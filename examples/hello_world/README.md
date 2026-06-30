# Hello World

See what OpenJury returns in under two minutes — no agent endpoint, no API keys.

## What you'll learn

- The shape of an `AgentEvalResult` (composite score, metrics, per-criterion breakdown)
- How `score_existing_response()` scores text you already have
- The difference between offline demo mode and live juror calls

## Prerequisites

| Mode | Requirements |
|------|--------------|
| Default (offline) | Python 3.11+, `pip install openjury` or editable install from repo root |
| `--live` | `export OPENAI_API_KEY="sk-..."` |

## Files

| File | Purpose |
|------|---------|
| `config.json` | Minimal jury config (2 jurors, 2 criteria, 2 assertions) |
| `score_existing.py` | Offline demo or live scoring script |

## Run

```bash
# Offline — no keys, always succeeds
python score_existing.py

# If running from the repo root:
uv run python examples/hello_world/score_existing.py

# Live — real juror LLM calls
export OPENAI_API_KEY="sk-..."
python score_existing.py --live
```

## Expected output

```
Offline demo — sample AgentEvalResult (no API keys required).

╔══ Quality Evaluation  (scale: 1–5) ══
  Jury:              Hello World Jury
  ...
  composite_score:   4.17 / 5  (0.834 normalized)
  assertion_score:   1.000
  assertions_passed: true
  passed:             true
  ...
```

The example also reports deterministic assertions beside the juror scores:

- `contains` verifies that the response mentions OpenJury.
- `not_contains` checks that it does not expose an internal server error.

See [`../assertions/`](../assertions/) for every supported assertion type.

## Next steps

- Evaluate a real agent endpoint → [`../basic_usage/`](../basic_usage/)
- Configure providers (OpenAI, OpenRouter, Ollama) → [`../provider_configs/`](../provider_configs/)
- Score without fetching in production → [`../../recipes/score-without-fetching.md`](../../recipes/score-without-fetching.md)
