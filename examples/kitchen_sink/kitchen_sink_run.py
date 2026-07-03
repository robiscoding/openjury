#!/usr/bin/env python3
"""Kitchen sink example — load a reference config and run offline or live evaluation.

Offline (default): validates config.json, resolves per-row assertion policies, and
scores canned responses without API keys.

Live: fetches agent responses and runs jurors over the inline dataset.

Usage:
    python kitchen_sink_run.py
    python kitchen_sink_run.py --live
    python kitchen_sink_run.py --live --limit 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from openjury import (  # noqa: E402
    JuryConfig,
    OpenJury,
    ResultFormatter,
    ScoreAggregator,
    evaluate_assertions,
    score_assertions,
)
from openjury.batch_dataset import (  # noqa: E402
    assertion_policy_for_case,
    cases_from_config,
)
from openjury.config import CriterionConfig  # noqa: E402
from openjury.endpoint_fetcher import load_endpoints_file  # noqa: E402
from openjury.execution import EvaluationItem, ExecutionOptions  # noqa: E402
from openjury.scoring import JurorScore  # noqa: E402

HERE = Path(__file__).parent

SAMPLE_RESPONSES = {
    "password-reset-001": (
        "Go to Settings → Security and click Forgot password. "
        "We will email you a reset link — never share your password with support."
    ),
    "order-status-001": (
        "Status: shipped. Your order #12345 will arrive Friday. "
        "Track it at https://example.com/orders/12345"
    ),
    "account-email-001": (
        "Open Account Settings → Profile, enter your new email, "
        "and confirm the verification message we send to both addresses."
    ),
    "baseline-check-001": (
        "Support is available Monday–Friday, 9am–6pm ET via chat or email."
    ),
}


def support_gated(
    juror_scores: List[JurorScore], criteria: List[CriterionConfig]
) -> float:
    """Zero composite when any juror rates helpfulness below 2."""
    for js in juror_scores:
        if js.criterion_scores.get("helpfulness", 5.0) < 2.0:
            return 0.0
    total_crit_w = sum(c.weight for c in criteria) or 1.0
    total_juror_w = sum(js.juror_weight for js in juror_scores) or 1.0
    return (
        sum(
            sum(
                js.criterion_scores.get(c.name, 0.0) * js.juror_weight
                for js in juror_scores
            )
            / total_juror_w
            * c.weight
            for c in criteria
        )
        / total_crit_w
    )


def build_evaluation_items(config: JuryConfig) -> List[EvaluationItem]:
    items: List[EvaluationItem] = []
    for case in cases_from_config(config):
        checks, assertion_threshold, quality_threshold = assertion_policy_for_case(
            case, config
        )
        items.append(
            EvaluationItem(
                item_id=case.case_id,
                prompt=case.prompt,
                ground_truth=case.ground_truth,
                assertions=checks or None,
                assertion_threshold=assertion_threshold,
                quality_threshold=quality_threshold,
            )
        )
    return items


def run_offline(config: JuryConfig) -> None:
    cases = cases_from_config(config)
    print(f"Loaded config: {config.name!r}")
    print(f"  jurors:           {len(config.jurors)}")
    print(f"  criteria:         {len(config.criteria)}")
    print(f"  assertion policies: {len(config.assertions)}")
    print(f"  dataset rows:     {len(config.dataset)}")
    print(f"  num_trials:       {config.num_trials}")
    print(f"  custom scoring:   {config.custom_scoring_function!r}")
    print()

    for case in cases:
        checks, assertion_threshold, quality_threshold = assertion_policy_for_case(
            case, config
        )
        sample = SAMPLE_RESPONSES.get(
            case.case_id,
            "This is a placeholder response for offline assertion checks.",
        )
        results = evaluate_assertions(sample, checks)
        assertion_score, assertions_passed = score_assertions(results)
        passed_threshold = (
            assertion_threshold is None or assertion_score >= assertion_threshold
        )
        print(f"=== {case.case_id} ===")
        print(f"prompt: {case.prompt!r}")
        if case.ground_truth:
            print(f"ground_truth: {case.ground_truth!r}")
        print(f"assertion_ids: {case.assertion_ids or '(none — juror scoring only)'}")
        print(f"checks resolved: {len(checks)}")
        for ar in results:
            status = "PASS" if ar.passed else "FAIL"
            print(f"  [{status}] {ar.name}: {ar.detail}")
        print(f"assertion_score:   {assertion_score:.3f}")
        print(f"assertions_passed: {assertions_passed}")
        if assertion_threshold is not None:
            print(
                f"assertion_threshold: {assertion_threshold:.3f} "
                f"({'met' if passed_threshold else 'missed'})"
            )
        if quality_threshold is not None:
            print(f"quality_threshold: {quality_threshold:.1f} (live mode only)")
        print()


def run_live(config: JuryConfig, limit: int | None) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "Error: --live requires OPENAI_API_KEY for juror LLM calls.",
            file=sys.stderr,
        )
        sys.exit(1)

    ScoreAggregator.register("support_gated", support_gated)
    try:
        jury = OpenJury(config)
        endpoint = load_endpoints_file(str(HERE / "endpoints.json"))[0]
        items = build_evaluation_items(config)
        if limit is not None:
            items = items[:limit]

        print(f"Evaluating {len(items)} dataset row(s) via {endpoint.alias}")
        print(f"Agent endpoint: {endpoint.url}")
        print(f"num_trials: {config.num_trials}")
        print()

        results = jury.evaluate_items(
            items,
            endpoint,
            options=ExecutionOptions(max_item_workers=1),
        )

        for item_result in results:
            case_id = item_result.item.item_id or f"item-{item_result.index}"
            if item_result.error is not None:
                print(f"=== {case_id} ERROR ===")
                print(item_result.error)
                print()
                continue
            result = item_result.result
            assert result is not None
            print(ResultFormatter.format_result(result))
            print()
            summary = {
                "case_id": case_id,
                "composite_score": result.composite_score,
                "assertion_score": result.assertion_score,
                "assertions_passed": result.assertions_passed,
                "passed": result.passed,
                "custom_metric": result.scored_metrics.custom,
            }
            if result.consistency_result is not None:
                summary["consistency"] = result.consistency_result.model_dump()
            print("Summary:")
            print(json.dumps(summary, indent=2))
            print()
    finally:
        ScoreAggregator.unregister("support_gated")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenJury kitchen sink example")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch agent responses and run jurors (requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max dataset rows to evaluate in live mode",
    )
    args = parser.parse_args()

    config = JuryConfig.from_json_file(str(HERE / "config.json"))

    if args.live:
        run_live(config, args.limit)
    else:
        print("Offline mode — config validation and deterministic assertion checks.")
        print("Tip: pass --live to evaluate against an agent (needs keys).\n")
        run_offline(config)


if __name__ == "__main__":
    main()
