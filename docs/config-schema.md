# Config Schema

Authoritative reference for `JuryConfig` JSON. Validate configs with:

```python
from openjury import JuryConfig
JuryConfig.from_json_file("config.json")
```

Machine-readable schema: [config.schema.json](config.schema.json) (regenerate with `python scripts/export_config_schema.py`).

## Unknown fields are rejected

Every config model sets `extra="forbid"`. A field OpenJury does not model raises
`ValidationError` at load time instead of being dropped:

```
JuryConfig.model_validate({..., "assertion_threshold": 0.8})
→ ValidationError: assertion_threshold — Extra inputs are not permitted
```

This is deliberate. A misspelled or misplaced key used to produce an evaluation that
quietly checked less than its author asked for, with no error and no warning. Two input
aliases exist for names people reach for first: `assertions` for
`global_assertions`, and `prompt` for `dataset[].input`. The generated JSON Schema lists
only the canonical name of each.

## Top-level fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Display name for this jury |
| `description` | no | `null` | Human-readable description |
| `llm_provider` | conditional* | `null` | Default provider for inheriting jurors |
| `criteria` | yes | — | List of evaluation criteria |
| `jurors` | yes | — | List of juror configs |
| `global_assertions` | no | `[]` | Deterministic checks applied to every item; alias `assertions` |
| `assertion_profiles` | no | `{}` | Reusable check groups keyed by profile ID |
| `assertion_policy` | no | `{}` | Default `assertion_threshold` (0–1) and `quality_threshold` (0–`score_scale`) |
| `dataset` | no | `[]` | Inline dataset rows |
| `score_scale` | no | `5` | Maximum score (2–10) |
| `score_min` | no | `1` | Minimum integer score; set to `0` to enable a 0–N axis |
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
| `base_url` | no | Endpoint override; works for `anthropic` gateways too |
| `extra_body` | no | Provider-specific request fields, forwarded verbatim |

## `criteria[]`

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Free-form string; juror JSON must use exact name |
| `description` | yes | — | What this criterion evaluates |
| `weight` | no | `1.0` | Importance in composite score |
| `rubric` | no | `null` | Exact score anchors (`"1"`) or inclusive ranges (`"1-2"`) |

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
| `extra_body` | no | `null` | Provider-specific request fields; settable on its own |

## Assertions

A deterministic check. Same shape wherever it appears: `global_assertions[]`,
`assertion_profiles.<id>.checks[]`, and `dataset[].assertions[]`.

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Identifier reported back on the result |
| `type` | yes | — | One of the 11 types below |
| `value` | yes | — | String; list of non-empty strings for `contains_any`/`contains_all`; non-negative integer for `min_length`/`max_length` |
| `case_sensitive` | no | `true` | `false` folds case on both sides |
| `required` | no | `true` | Whether failing it sets `assertions_passed` to false |
| `weight` | no | `1.0` | Contribution to `assertion_score`; must be > 0 |

Types: `contains`, `not_contains`, `equals`, `not_equals`, `starts_with`, `ends_with`,
`contains_any`, `contains_all`, `regex`, `min_length`, `max_length`.

Empty string values are rejected — a check against `""` is never what the author meant.
`regex` patterns are compiled at config load, so an invalid pattern fails fast rather
than at run time.

### Matching semantics

Pinned as data in [assertion_conformance.json](assertion_conformance.json), generated
from `evaluate_assertions` itself (regenerate with
`python scripts/export_assertion_conformance.py`). Consume it to prove a
reimplementation in another language agrees. The parts that surprise people:

- Case-insensitive matching uses Python's `str.casefold()`, not a plain lowercase: `ß`
  folds to `ss` and `ﬁ` to `fi`. It is locale-independent, so Turkish dotless `ı` does
  not fold together with `I`.
- `min_length` / `max_length` count Unicode code points. An emoji costs 1, a ZWJ family
  emoji costs 5.
- `regex` matches the **raw** response, not the case-normalized one, unlike every other
  type. `case_sensitive: false` applies `re.IGNORECASE` instead.
- `regex` patterns are Python `re`. Other dialects do not accept the same language.

### Which flag means "passed"

Three flags on `AgentEvalResult`, and reading only the first is the common bug:

| Flag | Means |
|------|-------|
| `assertions_passed` | Every check with `required: true` passed. Ignores `assertion_threshold` entirely |
| `assertion_threshold_met` | `assertion_score` (weighted pass rate over **all** checks) met `assertion_threshold`. `true` when none is configured |
| `quality_passed` | `composite_score` met `quality_threshold`. `true` when none is configured |

`passed` is the conjunction of all three, and is the flag to gate on. Neither threshold
changes `composite_score`.

Each `AssertionResult` also carries `scope` (`"global"`, `"profile"`, or `"inline"`) and
`profile_id`, so results can be aggregated across items without the config that produced
them — a check that failed twice means something different when it ran on every item
than when it ran on three.

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

### Unknown field

```json
{
  "name": "Typo Jury",
  "assertion_threshold": 0.8,
  "criteria": [{ "name": "x", "description": "y" }],
  "jurors": [{ "name": "Juror A" }]
}
```

**Error:** `assertion_threshold — Extra inputs are not permitted`. The threshold belongs
under `assertion_policy`; before `extra="forbid"` this config ran with no threshold at
all.

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
