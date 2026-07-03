"""Load batch evaluation cases from JSONL or CSV."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterator, List, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

from openjury.config import AssertionConfig, JuryConfig

logger = logging.getLogger(__name__)


class ExemplarItem(BaseModel):
    text: str
    reason: str = ""


class Exemplars(BaseModel):
    adequate: List[ExemplarItem] = Field(default_factory=list)
    inadequate: List[ExemplarItem] = Field(default_factory=list)
    rules: Optional[str] = None


class EndpointSpec(BaseModel):
    """Endpoint spec for inline use in batch dataset cases.

    Mirrors AgentEndpoint but lives here to avoid importing
    endpoint_fetcher (and httpx) at dataset-parse time.
    """

    url: str
    model_name: Optional[str] = None
    alias: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    request_body_template: Optional[dict[str, Any]] = None
    stream: bool = False
    response_path: str = "choices.0.message.content"
    timeout_s: float = 60.0


class BatchCase(BaseModel):
    """A single evaluation case in a batch dataset.

    ``endpoints`` may be empty when a global ``--endpoints-config``
    is supplied at run time; ``resolve_endpoint`` enforces that at
    least one source is available before fetching.
    """

    case_id: str
    prompt: str
    ground_truth: Optional[str] = None
    assertion_ids: List[str] = Field(default_factory=list)
    endpoints: List[EndpointSpec] = Field(default_factory=list)
    exemplars: Optional[Exemplars] = None
    assertions: Optional[List[AssertionConfig]] = None
    assertion_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    quality_threshold: Optional[float] = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_assertion_ids(cls, value: Any) -> Any:
        if isinstance(value, dict) and "assertion_ids" not in value:
            assertion_id = value.get("assertion_id")
            if assertion_id is not None:
                return {**value, "assertion_ids": [assertion_id]}
        return value

    @model_validator(mode="after")
    def validate_assertion_ids(self) -> "BatchCase":
        if any(not assertion_id for assertion_id in self.assertion_ids):
            raise ValueError("assertion_ids cannot contain empty strings")
        if len(self.assertion_ids) != len(set(self.assertion_ids)):
            raise ValueError("assertion_ids cannot contain duplicates")
        return self


def format_exemplars_for_jury(
    exemplars: Optional[Exemplars],
) -> tuple[Optional[str], Optional[str]]:
    """Return (references_text, case_rules) for OpenJury.score_response."""
    if exemplars is None:
        return None, None
    blocks: List[str] = []
    for i, ex in enumerate(exemplars.adequate, 1):
        suffix = f"\nWhy adequate: {ex.reason}" if ex.reason.strip() else ""
        blocks.append(f"**Adequate example {i}:**\n{ex.text.strip()}{suffix}")
    for i, ex in enumerate(exemplars.inadequate, 1):
        suffix = f"\nWhy inadequate: {ex.reason}" if ex.reason.strip() else ""
        blocks.append(f"**Inadequate example {i}:**\n{ex.text.strip()}{suffix}")
    references = "\n\n".join(blocks) if blocks else None
    rules = (
        exemplars.rules.strip() if exemplars.rules and exemplars.rules.strip() else None
    )
    return references, rules


def resolve_endpoint(
    case: BatchCase,
    global_endpoints: Optional[List[EndpointSpec]],
) -> "AgentEndpoint":  # type: ignore[name-defined]
    """Return the first AgentEndpoint to use for this batch case.

    Precedence (highest to lowest):
    1. Case-level ``endpoints`` (first entry)
    2. Global ``--endpoints-config`` endpoints (first entry)

    Raises EndpointFetchError if no endpoints are available.
    """
    from openjury.endpoint_fetcher import (  # local import avoids circular deps
        AgentEndpoint,
        EndpointFetchError,
    )

    endpoint_specs: Optional[List[EndpointSpec]] = None
    if case.endpoints:
        endpoint_specs = case.endpoints
    elif global_endpoints:
        endpoint_specs = global_endpoints

    if not endpoint_specs:
        raise EndpointFetchError(
            f"Case '{case.case_id}' has no endpoints and no global endpoints"
        )

    return AgentEndpoint.model_validate(endpoint_specs[0].model_dump())


def cases_from_config(config: JuryConfig) -> List[BatchCase]:
    """Convert inline JSON dataset rows into the existing batch case model."""
    cases: List[BatchCase] = []
    for item in config.dataset:
        cases.append(
            BatchCase(
                case_id=item.id,
                prompt=item.input,
                ground_truth=item.ground_truth,
                assertion_ids=item.assertion_ids,
                assertions=[],
            )
        )
    return cases


def assertion_policy_for_case(
    case: BatchCase, config: JuryConfig
) -> tuple[List[AssertionConfig], Optional[float], Optional[float]]:
    """Resolve a case reference, falling back to legacy inline case assertions."""
    if case.assertion_ids:
        unknown_ids = [
            assertion_id
            for assertion_id in case.assertion_ids
            if assertion_id not in config.assertions
        ]
        if unknown_ids:
            raise ValueError(
                f"Case '{case.case_id}' references unknown assertion_ids {unknown_ids}"
            )
        policies = [
            config.assertions[assertion_id] for assertion_id in case.assertion_ids
        ]
        checks = [check for policy in policies for check in policy.checks]
        assertion_thresholds = [
            policy.assertion_threshold
            for policy in policies
            if policy.assertion_threshold is not None
        ]
        quality_thresholds = [
            policy.quality_threshold
            for policy in policies
            if policy.quality_threshold is not None
        ]
        return (
            checks,
            max(assertion_thresholds) if assertion_thresholds else None,
            max(quality_thresholds) if quality_thresholds else None,
        )
    return (
        case.assertions or [],
        case.assertion_threshold,
        case.quality_threshold,
    )


def _parse_json_cell(raw: str, field: str) -> Any:
    raw = raw.strip()
    if not raw:
        raise ValueError(f"Missing required CSV column value: {field}")
    return json.loads(raw)


def load_cases(path: Path) -> List[BatchCase]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return list(iter_cases_jsonl(path))
    if suffix == ".csv":
        return list(iter_cases_csv(path))
    raise ValueError(f"Unsupported dataset format: {path} (use .jsonl or .csv)")


def iter_cases_jsonl(path: Path) -> Iterator[BatchCase]:
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                yield BatchCase.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                raise ValueError(f"{path}:{lineno}: {e}") from e


def iter_cases_csv(path: Path) -> Iterator[BatchCase]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path}: CSV has no header row")
        norm_fields = {h.strip() for h in reader.fieldnames if h and h.strip()}
        required = {"case_id", "prompt", "endpoints_json"}
        missing = required - norm_fields
        if missing:
            raise ValueError(f"{path}: CSV missing columns: {sorted(missing)}")
        for lineno, raw in enumerate(reader, start=2):
            row = {(k or "").strip(): v for k, v in raw.items()}
            try:
                exemplars_raw = (row.get("exemplars_json") or "").strip()
                meta_raw = (row.get("metadata_json") or "").strip()
                assertions_raw = (row.get("assertions_json") or "").strip()
                case_id = (row.get("case_id") or "").strip()
                prompt = (row.get("prompt") or "").strip()
                endpoints_cell = (row.get("endpoints_json") or "").strip()
                payload: dict[str, Any] = {
                    "case_id": case_id,
                    "prompt": prompt,
                    "endpoints": _parse_json_cell(endpoints_cell, "endpoints_json"),
                    "metadata": json.loads(meta_raw) if meta_raw else {},
                }
                ground_truth = (row.get("ground_truth") or "").strip()
                assertion_ids_raw = (row.get("assertion_ids_json") or "").strip()
                assertion_id = (row.get("assertion_id") or "").strip()
                if ground_truth:
                    payload["ground_truth"] = ground_truth
                if assertion_ids_raw:
                    payload["assertion_ids"] = json.loads(assertion_ids_raw)
                elif assertion_id:
                    payload["assertion_ids"] = [assertion_id]
                if exemplars_raw:
                    payload["exemplars"] = json.loads(exemplars_raw)
                if assertions_raw:
                    payload["assertions"] = json.loads(assertions_raw)
                assertion_threshold = (row.get("assertion_threshold") or "").strip()
                quality_threshold = (row.get("quality_threshold") or "").strip()
                if assertion_threshold:
                    payload["assertion_threshold"] = float(assertion_threshold)
                if quality_threshold:
                    payload["quality_threshold"] = float(quality_threshold)
                yield BatchCase.model_validate(payload)
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                raise ValueError(f"{path}: row {lineno}: {e}") from e


def eval_record(
    case_id: str,
    config_path: Optional[str],
    jury_name: str,
    eval_payload: Optional[dict[str, Any]],
    error: Optional[str],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "run_metadata": {
            "jury_name": jury_name,
            "config_path": config_path,
        },
        "error": error,
        "eval": eval_payload,
    }
