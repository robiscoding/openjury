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

from openjury import AgentResponse, JuryConfig, OpenJury, ResultFormatter
from openjury.output_format import AgentEvalResult, CriterionEvaluation, TrialResult
from openjury.scoring import JurorScore, ScoredMetrics

HERE = Path(__file__).parent

PROMPT = "Write a helpful response to demonstrate the system."
AGENT_TEXT = (
    "OpenJury evaluates agent responses using a panel of LLM judges. "
    "Each juror scores your response against configurable criteria, "
    "and the results are aggregated into rich quality metrics."
)


def demo_result() -> AgentEvalResult:
    """Canned result illustrating AgentEvalResult fields (no LLM calls)."""
    juror_scores = [
        JurorScore(
            juror_name="Expert Juror",
            juror_weight=2.0,
            criterion_scores={"factuality": 4.5, "clarity": 4.0},
            criterion_explanations={
                "factuality": "Accurate overview of OpenJury's purpose.",
                "clarity": "Clear and well-structured explanation.",
            },
        ),
        JurorScore(
            juror_name="General Juror",
            juror_weight=1.0,
            criterion_scores={"factuality": 4.0, "clarity": 4.5},
            criterion_explanations={
                "factuality": "Mostly accurate; minor simplification.",
                "clarity": "Easy to follow for a newcomer.",
            },
        ),
    ]
    metrics = ScoredMetrics(
        weighted_mean=4.17,
        mean=4.25,
        median=4.25,
        min_score=4.0,
        max_score=4.5,
        harmonic_mean=4.21,
        weakest_link=0.8,
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
    trial = TrialResult(
        trial_number=1,
        response_text=AGENT_TEXT,
        scored_metrics=metrics,
        criteria_evaluations=criteria_evaluations,
        juror_scores=juror_scores,
    )
    return AgentEvalResult(
        jury_name="Hello World Jury",
        prompt=PROMPT,
        score_scale=5,
        composite_score=metrics.weighted_mean,
        normalized_composite_score=metrics.weighted_mean / 5,
        scored_metrics=metrics,
        criteria_evaluations=criteria_evaluations,
        juror_scores=juror_scores,
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
    return jury.score_existing_response(
        prompt=PROMPT,
        agent_response=AgentResponse(content=AGENT_TEXT, model_name="demo-agent"),
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
    print(f"composite_score:            {result.composite_score:.2f}")
    print(f"normalized_composite_score: {result.normalized_composite_score:.3f}")
    print(f"juror_agreement:            {result.scored_metrics.juror_agreement:.3f}")


if __name__ == "__main__":
    main()
