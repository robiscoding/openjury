# Web Server Integration

Wrap OpenJury in a Flask HTTP API. Clients POST a prompt and an endpoint spec; the server fetches the agent response and returns an `AgentEvalResult`.

## What you'll learn

- Exposing OpenJury as an HTTP API with Flask
- Passing endpoint specs from clients with `${ENV_VAR}` credential resolution
- Serializing `AgentEvalResult` as JSON responses

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `pip install flask` | Not included in openjury core deps |
| `OPENROUTER_API_KEY` or `OPENAI_API_KEY` | Per your config |
| Agent or mock | For `/evaluate` calls |

## When to use this

Useful when:
- You want to call OpenJury from another service or frontend
- You have multiple teams that need shared access to a jury
- You want to run evaluations asynchronously via a queue

## API

### `POST /evaluate`

**Request body:**

```json
{
  "prompt": "How do I reset my password?",
  "endpoint": {
    "url": "http://localhost:8080/v1/chat/completions",
    "alias": "my-agent",
    "headers": { "Authorization": "Bearer ${AGENT_API_KEY}" },
    "request_body_template": {
      "model": "my-model",
      "messages": [{ "role": "user", "content": "{prompt}" }]
    },
    "response_path": "choices.0.message.content"
  },
  "references": "optional calibration text",
  "case_rules": "optional per-request juror instructions"
}
```

**Response (full):**

```json
{
  "composite_score": 4.1,
  "normalized_composite_score": 0.82,
  "score_scale": 5,
  "scored_metrics": {
    "weighted_mean": 4.1,
    "mean": 3.95,
    "median": 4.05,
    "min_score": 3.7,
    "max_score": 4.5,
    "harmonic_mean": 3.98,
    "weakest_link": 0.62,
    "juror_agreement": 0.91,
    "custom": null
  },
  "criteria_evaluations": { ... },
  "juror_scores": [ ... ],
  "consistency_result": null
}
```

**Response (simple — append `?simple` to the URL):**

```json
{
  "composite_score": 4.1,
  "normalized_composite_score": 0.82,
  "score_scale": 5
}
```

### `GET /health`

Returns `{"status": "healthy", "jury_initialized": true}`.

### `GET /jury/info`

Returns the jury configuration summary.

## Credential handling

Credentials in the endpoint `headers` are resolved from environment variables at request time. The client sends `"${MY_ENV_VAR}"` in the header value; the server expands it from its own environment.

The client never transmits raw API keys.

## Files

| File | Purpose |
|------|---------|
| `config.json` | Jury configuration loaded at server startup |
| `web_integration.py` | Flask app |

## Running

```bash
pip install flask
export OPENROUTER_API_KEY="..."
python web_integration.py
```

## Production notes

- This example runs Flask in debug mode on port 5000 — use a proper WSGI server (gunicorn, uvicorn) in production.
- Jury initialization is synchronous at startup. For high-concurrency deployments, consider pre-loading and sharing a single `OpenJury` instance (already done in the example).
- `score_response()` is blocking; wrap in a task queue (Celery, RQ) for async evaluation.

## Next steps

- [docs/composable-api.md](../../docs/composable-api.md)
- [recipes/crash-recovery-resume.md](../../recipes/crash-recovery-resume.md)
