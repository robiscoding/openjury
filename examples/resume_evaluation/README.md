# Resume Evaluation

Fetch an agent response, persist it, then score separately — the crash-recovery pattern for production pipelines.

## What you'll learn

- Splitting fetch and score with `fetch_agent_response()` and `score_existing_response()`
- Using `ExecutionOptions.idempotency_key` for traceability
- Handling partial juror failures with `raise_if_all_jurors_failed=False`

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `OPENAI_API_KEY` | Juror LLM calls |
| `AGENT_API_KEY` | Agent endpoint auth |
| Agent on `:8080` | Or run `python ../tools/mock_agent.py --port 8080` |

## Files

| File | Purpose |
|------|---------|
| `config.json` | Minimal jury config |
| `endpoints.json` | Agent endpoint spec |
| `resume_run.py` | Fetch → persist (simulated) → score |

## Run

```bash
# Terminal 1 (if no real agent)
python ../tools/mock_agent.py --port 8080

# Terminal 2
export OPENAI_API_KEY="..." AGENT_API_KEY=demo
python resume_run.py
```

## Expected output

```
Step 1: Fetch agent response (persist this in production)...
  Fetched 187 chars

Step 2: Score persisted response (no agent call)...
Composite score: 4.12
Juror agreement: 0.891
```

## Next steps

- [recipes/crash-recovery-resume.md](../../recipes/crash-recovery-resume.md)
- [docs/composable-api.md](../../docs/composable-api.md)
