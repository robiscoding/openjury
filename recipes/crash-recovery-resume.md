# Crash Recovery Resume

Separate agent fetching from juror scoring so you can retry after failures without re-calling your agent.

## Pattern

```python
from openjury import AgentResponse, ExecutionOptions, JuryConfig, OpenJury, fetch_agent_response
from openjury.endpoint_fetcher import AgentEndpoint

jury = OpenJury(JuryConfig.from_json_file("config.json"))
endpoint = AgentEndpoint(url="...", alias="agent")
options = ExecutionOptions(idempotency_key="run-abc123")

# Step 1: Fetch once, persist
fetch = fetch_agent_response(endpoint, prompt, options=options)
save_to_storage(fetch.response.content)  # your persistence layer

# Step 2: Score (retryable)
scoring = jury.score_existing_response(
    prompt=prompt,
    agent_response=AgentResponse(content=load_from_storage()),
    raise_if_all_jurors_failed=False,
)

if scoring.result:
    print(scoring.result.composite_score)
else:
    # Retry only failed jurors
    failed = [f.juror_name for f in scoring.juror_failures]
    retry = jury.score_existing_response(
        prompt=prompt,
        agent_response=AgentResponse(content=load_from_storage()),
        jurors_to_run=failed,
    )
```

## Runnable example

```bash
python examples/resume_evaluation/resume_run.py
```

## Related

- [docs/composable-api.md](../docs/composable-api.md)
- [examples/resume_evaluation/](../examples/resume_evaluation/)
