# Score Without Fetching

Use when you already have agent output — offline eval, unit tests, or re-scoring stored responses.

## When to use

- Testing jury configs without calling your agent
- Re-running jurors after a partial failure
- Evaluating logged production responses

## Code

```python
from openjury import AgentResponse, JuryConfig, OpenJury

jury = OpenJury(JuryConfig.from_json_file("config.json"))

result = jury.score_existing_response(
    prompt="How do I reset my password?",
    agent_response=AgentResponse(
        content="Go to Settings → Security → Reset Password.",
        model_name="my-agent-v2",
    ),
)

print(result.composite_score, result.scored_metrics.juror_agreement)
```

## Offline demo (no API keys)

```bash
python examples/hello_world/score_existing.py
```

Pass `--live` to run real jurors.

## Partial juror resume

```python
scoring = jury.score_existing_response(
    prompt="...",
    agent_response=AgentResponse(content="..."),
    jurors_to_run=["failed-juror-name"],
    raise_if_all_jurors_failed=False,
)
```

See [crash-recovery-resume.md](crash-recovery-resume.md).

## Related

- [examples/hello_world/](../examples/hello_world/)
- [docs/composable-api.md](../docs/composable-api.md)
