"""OpenJury hello world — see evaluation output without an agent endpoint.

Default (offline): prints a sample AgentEvalResult so you can inspect the output
shape with zero API keys.

Live mode: scores a hardcoded response with real juror LLM calls.

Usage:
    python score_existing.py              # offline demo (no keys)
    python score_existing.py --live       # requires OPENAI_API_KEY
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openjury import (
    AgentResponse,
    JuryConfig,
    OpenJury,
    ResultFormatter,
    evaluate_assertions,
    score_assertions,
)
from openjury.output_format import AgentEvalResult, CriterionEvaluation, TrialResult
from openjury.scoring import JurorScore, ScoredMetrics

HERE = Path(__file__).parent

PROMPT = "Write a helpful response to demonstrate the system."
AGENT_TEXT = (
    "OpenJury evaluates agent responses using a panel of LLM judges. "
    "Each juror scores your response against configurable criteria, "
    "and the results are aggregated into rich quality metrics."
)
ITEM_ID = "hello-world-001"
METADATA = {"example": "hello_world", "track": "quickstart"}
QUALITY_THRESHOLD = 4.0
CONTESTED_THRESHOLD = 0.6


def demo_result() -> AgentEvalResult:
    """Canned result illustrating AgentEvalResult fields (no LLM calls)."""
    config = JuryConfig.from_json_file(str(HERE / "config.json"))
    assertion_results = evaluate_assertions(AGENT_TEXT, config.global_assertions)
    assertion_score, assertions_passed = score_assertions(assertion_results)
    juror_scores = [
        JurorScore(
            juror_name="Expert Juror",
            juror_weight=2.0,
            criterion_scores={"factuality": 4.5, "clarity": 4.0},
            criterion_explanations={
                "factuality": "Accurate overview of OpenJury's purpose.",
                "clarity": "Clear and well-structured explanation.",
            },
            latency_ms=1180,
        ),
        JurorScore(
            juror_name="General Juror",
            juror_weight=1.0,
            criterion_scores={"factuality": 4.0, "clarity": 4.5},
            criterion_explanations={
                "factuality": "Mostly accurate; minor simplification.",
                "clarity": "Easy to follow for a newcomer.",
            },
            latency_ms=940,
        ),
    ]
    metrics = ScoredMetrics(
        weighted_mean=4.17,
        mean=4.25,
        median=4.25,
        min_score=4.0,
        max_score=4.5,
        harmonic_mean=4.21,
        weakest_link=4.17,
        juror_agreement=0.92,
    )
    criteria_evaluations = {
        "factuality": CriterionEvaluation(
            weighted_mean_score=4.33,
            min_juror_score=4.0,
            max_juror_score=4.5,
            juror_agreement=0.94,
            weight=2.0,
            explanations={
                "Expert Juror": juror_scores[0].criterion_explanations["factuality"],
                "General Juror": juror_scores[1].criterion_explanations["factuality"],
            },
        ),
        "clarity": CriterionEvaluation(
            weighted_mean_score=4.17,
            min_juror_score=4.0,
            max_juror_score=4.5,
            juror_agreement=0.91,
            weight=1.0,
            explanations={
                "Expert Juror": juror_scores[0].criterion_explanations["clarity"],
                "General Juror": juror_scores[1].criterion_explanations["clarity"],
            },
        ),
    }
    lowest_criterion = min(
        criteria_evaluations,
        key=lambda name: criteria_evaluations[name].weighted_mean_score,
    )
    quality_passed = metrics.weighted_mean >= QUALITY_THRESHOLD
    trial = TrialResult(
        trial_number=1,
        response_text=AGENT_TEXT,
        scored_metrics=metrics,
        criteria_evaluations=criteria_evaluations,
        juror_scores=juror_scores,
        assertion_results=assertion_results,
        assertion_score=assertion_score,
        assertions_passed=assertions_passed,
    )
    return AgentEvalResult(
        jury_name="Hello World Jury",
        prompt=PROMPT,
        model_name="demo-agent",
        score_scale=5,
        composite_score=metrics.weighted_mean,
        normalized_composite_score=metrics.weighted_mean / 5,
        scored_metrics=metrics,
        criteria_evaluations=criteria_evaluations,
        juror_scores=juror_scores,
        assertion_results=assertion_results,
        assertion_score=assertion_score,
        assertions_passed=assertions_passed,
        passed=assertions_passed and quality_passed,
        quality_passed=quality_passed,
        assertion_threshold_met=True,
        quality_threshold=QUALITY_THRESHOLD,
        item_id=ITEM_ID,
        metadata=METADATA,
        lowest_criterion=lowest_criterion,
        lowest_criterion_score=criteria_evaluations[
            lowest_criterion
        ].weighted_mean_score,
        contested=metrics.juror_agreement < CONTESTED_THRESHOLD,
        evaluation_duration_ms=850,
        trial_results=[trial],
    )


def run_live() -> AgentEvalResult:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "Error: --live requires OPENAI_API_KEY.\n"
            "Run without --live for an offline demo, or export your key:\n"
            "  export OPENAI_API_KEY='sk-...'",
            file=sys.stderr,
        )
        sys.exit(1)

    config = JuryConfig.from_json_file(str(HERE / "config.json"))
    jury = OpenJury(config)
    result = jury.score_existing_response(
        prompt=PROMPT,
        agent_response=AgentResponse(content=AGENT_TEXT, model_name="demo-agent"),
        quality_threshold=QUALITY_THRESHOLD,
    )
    return result.model_copy(
        update={
            "item_id": ITEM_ID,
            "metadata": {**METADATA, "mode": "live"},
        }
    )


def _fmt_threshold(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def print_extended_stats(result: AgentEvalResult) -> None:
    """Print per-item stats used by batch dashboards and execution tables."""
    scale = result.score_scale
    print("── Extended stats ──")
    print(f"  status:                   {result.status}")
    print(f"  item_id:                  {result.item_id or 'n/a'}")
    print(f"  metadata:                 {result.metadata or {}}")
    print(
        f"  composite_score:          {result.composite_score:.2f} / {scale}  "
        f"({result.normalized_composite_score:.3f} normalized)"
    )
    print(f"  passed:                   {result.passed}")
    print(f"  quality_passed:           {result.quality_passed}")
    print(f"  assertions_passed:        {result.assertions_passed}")
    print(f"  assertion_threshold_met:  {result.assertion_threshold_met}")
    print(f"  quality_threshold:        {_fmt_threshold(result.quality_threshold)}")
    print(f"  assertion_threshold:      {_fmt_threshold(result.assertion_threshold)}")
    print(f"  assertion_score:          {result.assertion_score:.3f}")
    print(f"  juror_agreement:          {result.scored_metrics.juror_agreement:.3f}")
    print(f"  contested:                {result.contested}")
    print(
        f"  lowest_criterion:         "
        f"{result.lowest_criterion or 'n/a'}"
        + (
            f" ({result.lowest_criterion_score:.2f})"
            if result.lowest_criterion_score is not None
            else ""
        )
    )
    print(f"  min_juror_total:          {result.scored_metrics.min_score:.2f}")
    print(f"  max_juror_total:          {result.scored_metrics.max_score:.2f}")
    print(f"  weakest_link:             {result.scored_metrics.weakest_link:.2f}")
    if result.evaluation_duration_ms is not None:
        print(f"  evaluation_duration_ms:   {result.evaluation_duration_ms}")
    if result.fetch_metadata is not None and result.fetch_metadata.total_latency_ms:
        print(f"  agent_latency_ms:         {result.fetch_metadata.total_latency_ms}")
    if result.juror_failures:
        print(f"  juror_failures:           {len(result.juror_failures)}")
        for failure in result.juror_failures:
            print(f"    - {failure.juror_name}: {failure.code}")

    print()
    print("  Per-criterion:")
    for name, criterion in result.criteria_evaluations.items():
        print(
            f"    {name:<12} mean={criterion.weighted_mean_score:.2f}  "
            f"agreement={criterion.juror_agreement:.2f}  "
            f"min={criterion.min_juror_score:.1f}"
        )

    print()
    print("  Per-juror:")
    panel_mean = result.composite_score
    for juror in result.juror_scores:
        total_weight = sum(c.weight for c in result.criteria_evaluations.values())
        juror_total = (
            sum(
                juror.criterion_scores.get(name, 0.0) * criterion.weight
                for name, criterion in result.criteria_evaluations.items()
            )
            / total_weight
            if total_weight
            else 0.0
        )
        tendency = juror_total - panel_mean
        latency = f"{juror.latency_ms}ms" if juror.latency_ms is not None else "n/a"
        print(
            f"    {juror.juror_name:<14} total={juror_total:.2f}  "
            f"tendency={tendency:+.2f}  latency={latency}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenJury hello world example")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run real juror LLM calls (requires OPENAI_API_KEY)",
    )
    args = parser.parse_args()

    if args.live:
        print("Running live evaluation with real jurors...\n")
        result = run_live()
    else:
        print("Offline demo — sample AgentEvalResult (no API keys required).\n")
        print("Tip: pass --live to score with real jurors (needs OPENAI_API_KEY).\n")
        result = demo_result()

    print(ResultFormatter.format_result(result))
    print()
    print_extended_stats(result)


if __name__ == "__main__":
    main()
