#!/usr/bin/env python3
"""
Consistency Audit Example

When num_trials > 1, OpenJury calls the agent endpoint multiple times for the
same prompt, evaluates each response independently, then measures how consistently
the agent produces similar-quality output.

This is useful for:
- Detecting LLMs with high temperature that produce highly variable responses
- Validating that a prompt produces reliably good outputs before shipping
- Comparing agent configurations for stability, not just peak quality

The primary quality score (composite_score) always comes from trial 1.
The consistency_result captures how much the scores vary across trials.

Usage:
    export OPENROUTER_API_KEY="..."
    export AGENT_API_KEY="..."
    python consistency_run.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openjury import JuryConfig, OpenJury, ResultFormatter
from openjury.endpoint_fetcher import AgentEndpoint

HERE = Path(__file__).parent


def main() -> None:
    jury_config = JuryConfig.from_json_file(str(HERE / "config.json"))
    jury = OpenJury(jury_config)

    print(f"Jury: {jury_config.name}")
    print(f"Trials: {jury_config.num_trials}")
    print(f"Score scale: 1–{jury_config.score_scale}")
    print()

    endpoint = AgentEndpoint(
        url="http://localhost:8080/v1/chat/completions",
        alias="my-agent",
        headers={"Authorization": "Bearer ${AGENT_API_KEY}"},
        request_body_template={
            "model": "my-model",
            "messages": [{"role": "user", "content": "{prompt}"}],
        },
    )

    prompt = "My order hasn't arrived after 10 days. What should I do?"

    print(f"Prompt: {prompt!r}")
    print()

    result = jury.score_response(prompt=prompt, endpoint=endpoint)

    # Print the formatted output — includes the consistency section automatically
    print(ResultFormatter.format_result(result))
    print()

    # Programmatic access
    cr = result.consistency_result
    if cr is not None:
        print("Programmatic consistency access:")
        print(f"  num_trials:              {cr.num_trials}")
        print(
            f"  score_std:               {cr.score_std:.3f}  ← headline consistency metric"
        )
        print(f"  score_mean:              {cr.score_mean:.3f}  (informational only)")
        print(f"  score_min / score_max:   {cr.score_min:.3f} / {cr.score_max:.3f}")
        print(f"  trial scores:            {cr.trial_composite_scores}")
        print(f"  interpretation:          {cr.interpretation}")
        print()

        # Deciding whether to deploy
        if cr.score_std < 0.1:
            print("Decision: agent is consistent — safe to deploy.")
        elif cr.score_std < 0.3:
            print(
                "Decision: moderate variance — review agent temperature before deploying."
            )
        else:
            print(
                "Decision: high variance — agent is unpredictable; investigate before deploying."
            )

    # Per-trial data (for deep analysis)
    if result.trial_results:
        print()
        print("Per-trial breakdown:")
        for tr in result.trial_results:
            print(
                f"  Trial {tr.trial_number}: "
                f"composite={tr.scored_metrics.weighted_mean:.2f}  "
                f"agreement={tr.scored_metrics.juror_agreement:.2f}"
            )
            preview = tr.response_text[:80].replace("\n", " ")
            print(f"    response preview: {preview!r}...")


if __name__ == "__main__":
    main()
