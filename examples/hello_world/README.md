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
| `config.json` | Minimal jury config (2 jurors, 2 criteria) |
| `score_existing.py` | Offline demo or live scoring script |

## Run

```bash
# Offline — no keys, always succeeds
python score_existing.py

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
  ...
```

## Next steps

- Evaluate a real agent endpoint → [`../basic_usage/`](../basic_usage/)
- Configure providers (OpenAI, OpenRouter, Ollama) → [`../provider_configs/`](../provider_configs/)
- Score without fetching in production → [`../../recipes/score-without-fetching.md`](../../recipes/score-without-fetching.md)
