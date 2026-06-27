"""Resume evaluation after persisting an agent response (crash-recovery pattern).

Demonstrates the fetch/score split: fetch once, persist the text, score later
(or retry scoring after a partial juror failure).

Usage:
    export OPENAI_API_KEY="..." AGENT_API_KEY=demo
    python resume_run.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openjury import AgentResponse, ExecutionOptions, JuryConfig, OpenJury
from openjury.endpoint_fetcher import fetch_agent_response, load_endpoints_file

HERE = Path(__file__).parent


def main() -> None:
    jury = OpenJury(JuryConfig.from_json_file(str(HERE / "config.json")))
    endpoint = load_endpoints_file(str(HERE / "endpoints.json"))[0]
    prompt = "How do I reset my password?"
    options = ExecutionOptions(idempotency_key="exe_demo_1")

    print("Step 1: Fetch agent response (persist this in production)...")
    fetch = fetch_agent_response(endpoint, prompt, options=options)
    persisted_response = fetch.response.content
    print(f"  Fetched {len(persisted_response)} chars\n")

    print("Step 2: Score persisted response (no agent call)...")
    scoring = jury.score_existing_response(
        prompt=prompt,
        agent_response=AgentResponse(content=persisted_response),
        options=options,
        raise_if_all_jurors_failed=False,
    )

    if scoring.result is None:
        print("All jurors failed:", scoring.juror_failures)
        return

    print(f"Composite score: {scoring.result.composite_score:.2f}")
    print(f"Juror agreement: {scoring.result.scored_metrics.juror_agreement:.3f}")


if __name__ == "__main__":
    main()
