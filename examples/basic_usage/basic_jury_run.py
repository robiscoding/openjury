"""Basic OpenJury agent evaluation example.

Loads a jury config, calls an agent endpoint for a single prompt, and
prints the composite quality score with a full per-criterion breakdown.

Usage:
    export AGENT_API_KEY="..."          # used by endpoints.json for Bearer auth
    python basic_jury_run.py

Environment:
    OPENAI_API_KEY  — juror models (see config.json llm_provider)
    AGENT_API_KEY   — your agent endpoint API key (used in endpoints.json)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openjury import JuryConfig, OpenJury, ResultFormatter, ScoreAggregator
from openjury.endpoint_fetcher import load_endpoints_file

HERE = Path(__file__).parent


def main() -> None:
    jury_config = JuryConfig.from_json_file(str(HERE / "config.json"))
    endpoints = load_endpoints_file(str(HERE / "endpoints.json"))
    endpoint = endpoints[0]

    # Optional: register a custom scoring function.
    # It receives all juror scores and criteria; must return a single float.
    def penalise_low_accuracy(juror_scores, criteria):
        """Zero out the composite score if any juror rates accuracy below 2."""
        for js in juror_scores:
            if js.criterion_scores.get("accuracy", 5) < 2:
                return 0.0
        # fall back to simple weighted mean
        total_w = sum(c.weight for c in criteria) or 1.0
        return (
            sum(
                sum(
                    js.criterion_scores.get(c.name, 0) * js.juror_weight
                    for js in juror_scores
                )
                / (sum(js.juror_weight for js in juror_scores) or 1.0)
                * c.weight
                for c in criteria
            )
            / total_w
        )

    ScoreAggregator.register("penalise_low_accuracy", penalise_low_accuracy)

    prompt = "How do I reset my password?"

    print(f"Evaluating: {prompt!r}")
    print(f"Agent:      {endpoint.alias} ({endpoint.url})")
    print()

    result = jury_config_run(jury_config, endpoint, prompt)

    print(ResultFormatter.format_result(result))
    print()

    print("JSON summary:")
    print(
        json.dumps(
            {
                "composite_score": result.composite_score,
                "normalized_composite_score": result.normalized_composite_score,
                "score_scale": result.score_scale,
                "scored_metrics": result.scored_metrics.model_dump(),
            },
            indent=2,
        )
    )

    ScoreAggregator.unregister("penalise_low_accuracy")


def jury_config_run(jury_config, endpoint, prompt):
    jury = OpenJury(jury_config)
    return jury.score_response(prompt=prompt, endpoint=endpoint)


if __name__ == "__main__":
    main()
