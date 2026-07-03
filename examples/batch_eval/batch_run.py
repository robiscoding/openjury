#!/usr/bin/env python3
"""Batch-run OpenJury agent evaluation over a JSONL or CSV dataset (see README.md)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from openjury import JuryConfig, OpenJury  # noqa: E402
from openjury.batch_dataset import (  # noqa: E402
    EndpointSpec,
    assertion_policy_for_case,
    eval_record,
    format_exemplars_for_jury,
    load_cases,
    resolve_endpoint,
)
from openjury.endpoint_fetcher import load_endpoints_file  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger("batch_run")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run OpenJury agent evaluation on a batch dataset."
    )
    parser.add_argument("--config", required=True, help="Path to jury_config.json")
    parser.add_argument(
        "--dataset", required=True, help="Path to .jsonl or .csv dataset"
    )
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument(
        "--endpoints-config",
        default=None,
        help="Path to endpoints JSON file (fallback for cases with no inline endpoints)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max cases to run")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    dataset_path = Path(args.dataset).resolve()
    output_path = Path(args.output).resolve()

    global_endpoint_specs: Optional[list[EndpointSpec]] = None
    if args.endpoints_config:
        raw = load_endpoints_file(args.endpoints_config)
        global_endpoint_specs = [
            EndpointSpec.model_validate(ep.model_dump()) for ep in raw
        ]

    jury_config = JuryConfig.from_json_file(str(config_path))
    jury = OpenJury(jury_config)
    cases = load_cases(dataset_path)
    if args.limit is not None:
        cases = cases[: args.limit]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_str = str(config_path)

    with output_path.open("w", encoding="utf-8") as out_f:
        for case in cases:
            refs, rules = format_exemplars_for_jury(case.exemplars)
            row_error = None
            eval_payload = None
            try:
                endpoint = resolve_endpoint(case, global_endpoint_specs)
                assertions, assertion_threshold, quality_threshold = (
                    assertion_policy_for_case(case, jury_config)
                )
                result = jury.score_response(
                    prompt=case.prompt,
                    endpoint=endpoint,
                    references=refs,
                    case_rules=rules,
                    assertions=assertions,
                    assertion_threshold=assertion_threshold,
                    quality_threshold=quality_threshold,
                )
                eval_payload = {
                    "composite_score": result.composite_score,
                    "normalized_composite_score": result.normalized_composite_score,
                    "assertion_score": result.assertion_score,
                    "assertions_passed": result.assertions_passed,
                    "passed": result.passed,
                    "score_scale": result.score_scale,
                    "scored_metrics": result.scored_metrics.model_dump(),
                    "criteria_evaluations": {
                        name: ce.model_dump()
                        for name, ce in result.criteria_evaluations.items()
                    },
                    "consistency_result": (
                        result.consistency_result.model_dump()
                        if result.consistency_result
                        else None
                    ),
                }
            except Exception as e:
                row_error = str(e)
                logger.exception("Case %s failed", case.case_id)

            record = eval_record(
                case_id=case.case_id,
                config_path=cfg_str,
                jury_name=jury_config.name,
                eval_payload=eval_payload,
                error=row_error,
            )
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")

            status = "ok" if row_error is None else f"error: {row_error}"
            logger.info("%s %s", case.case_id, status)

    logger.info("Wrote %s rows to %s", len(cases), output_path)


if __name__ == "__main__":
    main()
