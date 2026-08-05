# Provider Configuration

Juror LLM credentials are configured in `JuryConfig` — not environment variables like `LLM_PROVIDER`.

## Resolution rules

1. **Default:** jurors inherit the jury-level `llm_provider` bundle.
2. **Override:** set all three on a juror — `model_name`, `api_key`, `provider`.
3. **No merging:** overrides replace the bundle entirely (optional `base_url` on the juror).

Partial overrides (e.g. only `model_name`) fail validation at config load time.

`extra_body` is the one exception to rule 2: a juror may set it alone, keeping
the inherited credentials. It replaces (never merges with) the jury-level value.

## openai_compatible

Works with OpenAI, OpenRouter, xAI, Gemini, Ollama, vLLM, LiteLLM, and any OpenAI-compatible API.

```json
"llm_provider": {
  "provider": "openai_compatible",
  "model_name": "gpt-4o-mini",
  "api_key": "${OPENAI_API_KEY}"
}
```

OpenRouter:

```json
"llm_provider": {
  "provider": "openai_compatible",
  "model_name": "openai/gpt-4o-mini",
  "api_key": "${OPENROUTER_API_KEY}",
  "base_url": "https://openrouter.ai/api/v1"
}
```

Ollama (local):

```json
"llm_provider": {
  "provider": "openai_compatible",
  "model_name": "llama3.2",
  "api_key": "ollama",
  "base_url": "http://localhost:11434/v1"
}
```

## anthropic

Requires `pip install openjury[anthropic]`.

Per-juror override:

```json
{
  "name": "Claude Juror",
  "model_name": "claude-sonnet-4-20250514",
  "provider": "anthropic",
  "api_key": "${ANTHROPIC_API_KEY}",
  "weight": 1.0
}
```

`base_url` also applies to Anthropic, for gateways and proxies that speak the
Anthropic wire format. Leave it unset to call the Anthropic API directly.

## Provider-specific request fields (`extra_body`)

`extra_body` is merged into every juror request for that provider and forwarded
verbatim — OpenJury neither interprets nor validates its keys. Use it for
features a specific provider offers that are not part of OpenJury's own config.

OpenRouter provider routing and cost reporting:

```json
"llm_provider": {
  "provider": "openai_compatible",
  "model_name": "openai/gpt-oss-20b",
  "api_key": "${OPENROUTER_API_KEY}",
  "base_url": "https://openrouter.ai/api/v1",
  "extra_body": {
    "provider": {
      "sort": "price",
      "allow_fallbacks": true,
      "max_price": { "prompt": 0.20, "completion": 0.60 },
      "data_collection": "deny"
    },
    "usage": { "include": true }
  }
}
```

That block lets OpenRouter fail over to another upstream on a 429 instead of
failing the juror, caps the per-request price, and asks for the authoritative
cost back on the response (see token usage below).

Keys OpenJury sets itself — `model`, `messages`, `temperature`, and Anthropic's
`max_tokens` and `system` — are not overridable through `extra_body`.

## Token usage

Each `JurorScore` carries an optional `usage: TokenUsage` with whatever the
provider reported:

| Field | Notes |
|-------|-------|
| `prompt_tokens` | Anthropic's `input_tokens`; excludes cache reads |
| `completion_tokens` | Anthropic's `output_tokens` |
| `total_tokens` | As reported; summed from parts on Anthropic |
| `cached_tokens` | OpenAI `prompt_tokens_details.cached_tokens`, Anthropic `cache_read_input_tokens` |
| `cost` | Only when the provider returns it (OpenRouter, with `usage.include`) |
| `model` | The model that actually served the call, which a router may change |

Every field is optional — providers differ in what they report, and `usage` is
`None` when nothing was reported. A `JurorFailure` carries the same field: a
call that reached the provider and came back unusable was still billed, so
those tokens are reported rather than dropped.

## Mixed-provider jury

```json
{
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
  ]
}
```

## Environment variable interpolation

Both `api_key` and `base_url` support `${VAR_NAME}` expanded at `Juror` init time. Missing vars raise `ConfigurationError`.

## Ready-to-use configs

| Setup | File |
|-------|------|
| OpenAI direct | `examples/provider_configs/openai_direct.json` |
| OpenRouter | `examples/provider_configs/openrouter.json` |
| Multi-model OpenRouter | `examples/provider_configs/openrouter_multi_model.json` |
| Mixed OpenAI + Anthropic | `examples/provider_configs/mixed_providers.json` |
| Ollama local | `examples/provider_configs/ollama_local.json` |
| Self-hosted gateway | `examples/provider_configs/self_hosted_gateway.json` |
| All jurors override | `examples/provider_configs/no_global_all_overrides.json` |

See [examples/provider_configs/README.md](../examples/provider_configs/README.md).

## Recipes

- [OpenRouter on a budget](../recipes/openrouter-on-a-budget.md)
- [Local Ollama jury](../recipes/local-ollama-jury.md)
- [Mixed provider jury](../recipes/mixed-provider-jury.md)
