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

from openjury import (  # noqa: E402
    EvaluationItem,
    ExecutionOptions,
    JuryConfig,
    OpenJury,
)
from openjury.batch_dataset import (  # noqa: E402
    EndpointSpec,
    assertion_policy_for_case,
    format_exemplars_for_jury,
    item_eval_to_record,
    load_cases,
    resolve_endpoint,
    serialize_batch_run_summary,
)
from openjury.endpoint_fetcher import load_endpoints_file  # noqa: E402
from openjury.output_format import serialize_eval_result  # noqa: E402

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
        "--summary-output",
        default=None,
        help="Optional path for batch run summary JSON",
    )
    parser.add_argument(
        "--endpoints-config",
        default=None,
        help="Path to endpoints JSON file (fallback for cases with no inline endpoints)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max cases to run")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent case evaluations",
    )
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

    evaluation_items: list[EvaluationItem] = []
    case_ids: list[str] = []
    for case in cases:
        refs, rules = format_exemplars_for_jury(case.exemplars)
        endpoint = resolve_endpoint(case, global_endpoint_specs)
        assertions, assertion_threshold, quality_threshold = assertion_policy_for_case(
            case, jury_config
        )
        evaluation_items.append(
            EvaluationItem(
                prompt=case.prompt,
                item_id=case.case_id,
                ground_truth=case.ground_truth,
                assertions=assertions,
                assertion_threshold=assertion_threshold,
                quality_threshold=quality_threshold,
                metadata=case.metadata,
                endpoint=endpoint,
                references=refs,
                case_rules=rules,
            )
        )
        case_ids.append(case.case_id)

    batch_result = jury.evaluate_items_with_summary(
        evaluation_items,
        options=ExecutionOptions(max_item_workers=max(1, args.workers)),
    )

    with output_path.open("w", encoding="utf-8") as out_f:
        for case_id, item_result in zip(case_ids, batch_result.items):
            eval_payload = (
                serialize_eval_result(item_result.result)
                if item_result.result is not None
                else None
            )
            record = item_eval_to_record(
                item_result,
                case_id=case_id,
                config_path=cfg_str,
                jury_name=jury_config.name,
                eval_payload=eval_payload,
            )
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            status = record.get("status", "scored")
            logger.info(
                "%s %s",
                case_id,
                status if status == "scored" else f"error: {record.get('error')}",
            )

    if args.summary_output:
        summary_path = Path(args.summary_output).resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_payload = serialize_batch_run_summary(
            batch_result.summary,
            jury_name=jury_config.name,
            config_path=cfg_str,
            started_at=batch_result.started_at,
            finished_at=batch_result.finished_at,
            duration_ms=batch_result.duration_ms,
            worker_count=max(1, args.workers),
        )
        summary_path.write_text(
            json.dumps(summary_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Wrote summary to %s", summary_path)

    logger.info("Wrote %s rows to %s", len(cases), output_path)


if __name__ == "__main__":
    main()
