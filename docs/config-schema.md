# Config Schema

Authoritative reference for `JuryConfig` JSON. Validate configs with:

```python
from openjury import JuryConfig
JuryConfig.from_json_file("config.json")
```

Machine-readable schema: [config.schema.json](config.schema.json) (regenerate with `python scripts/export_config_schema.py`).

## Top-level fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Display name for this jury |
| `description` | no | `null` | Human-readable description |
| `llm_provider` | conditional* | `null` | Default provider for inheriting jurors |
| `criteria` | yes | — | List of evaluation criteria |
| `jurors` | yes | — | List of juror configs |
| `score_scale` | no | `5` | All scores on 1–N axis (2–10) |
| `num_trials` | no | `1` | 1 = quality; >1 = consistency audit (max 5) |
| `custom_scoring_function` | no | `null` | Registered custom scorer name |
| `require_explanation` | no | `true` | Jurors must explain scores |
| `max_retries` | no | `3` | Retries per juror on parse/API failure |

\*Required unless **every** juror sets `model_name`, `api_key`, and `provider` together.

## `llm_provider`

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | yes | `"openai_compatible"` or `"anthropic"` |
| `model_name` | yes | Model identifier |
| `api_key` | yes | Supports `${ENV_VAR}` |
| `base_url` | no | For non-OpenAI compatible endpoints |

## `criteria[]`

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Free-form string; juror JSON must use exact name |
| `description` | yes | — | What this criterion evaluates |
| `weight` | no | `1.0` | Importance in composite score |
| `rubric` | no | `null` | Score anchors keyed by level (`"1"`, `"3"`, `"5"`) |

## `jurors[]`

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Juror identifier |
| `weight` | no | `1.0` | Influence in weighted mean |
| `temperature` | no | `0.1` | LLM temperature (0–2) |
| `system_prompt` | no | `null` | Custom juror persona |
| `model_name` | override | `null` | Must set with `api_key` + `provider` |
| `api_key` | override | `null` | Must set with `model_name` + `provider` |
| `provider` | override | `null` | Must set with `model_name` + `api_key` |
| `base_url` | no | `null` | Only when fully overriding |

## Valid examples

### Minimal valid config

```json
{
  "name": "Minimal Jury",
  "llm_provider": {
    "provider": "openai_compatible",
    "model_name": "gpt-4o-mini",
    "api_key": "${OPENAI_API_KEY}"
  },
  "criteria": [
    {
      "name": "helpfulness",
      "description": "Does it help?",
      "weight": 1.0
    }
  ],
  "jurors": [
    { "name": "Juror A", "weight": 1.0 }
  ]
}
```

### Per-juror override (valid)

```json
{
  "name": "Mixed Jury",
  "llm_provider": {
    "provider": "openai_compatible",
    "model_name": "gpt-4o-mini",
    "api_key": "${OPENAI_API_KEY}"
  },
  "jurors": [
    { "name": "GPT Juror", "weight": 1.0 },
    {
      "name": "Claude Juror",
      "model_name": "claude-sonnet-4-20250514",
      "provider": "anthropic",
      "api_key": "${ANTHROPIC_API_KEY}",
      "weight": 1.0
    }
  ],
  "criteria": [
    { "name": "accuracy", "description": "Is it correct?", "weight": 1.0 }
  ]
}
```

## Invalid examples

### Partial juror override

```json
{
  "jurors": [
    { "name": "Bad Juror", "model_name": "gpt-4o" }
  ]
}
```

**Error:** `Juror 'Bad Juror' must set model_name, api_key, and provider together...`

### Missing llm_provider with inheriting jurors

```json
{
  "name": "No Provider",
  "jurors": [{ "name": "Juror A" }],
  "criteria": [{ "name": "x", "description": "y" }]
}
```

**Error:** `ConfigurationError` at juror init — no credentials to inherit.

### Unset environment variable

```json
"api_key": "${OPENAI_API_KEY}"
```

**Error:** `ConfigurationError` if `OPENAI_API_KEY` is not exported before `OpenJury(...)`.

## Ready-to-use configs

Copy from [`examples/provider_configs/`](../examples/provider_configs/) for OpenAI, OpenRouter, Ollama, mixed providers, and all-override setups.

See also [provider-config.md](provider-config.md) for resolution rules.
