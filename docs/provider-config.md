# Provider Configuration

Juror LLM credentials are configured in `JuryConfig` — not environment variables like `LLM_PROVIDER`.

## Resolution rules

1. **Default:** jurors inherit the jury-level `llm_provider` bundle.
2. **Override:** set all three on a juror — `model_name`, `api_key`, `provider`.
3. **No merging:** overrides replace the bundle entirely (optional `base_url` on the juror).

Partial overrides (e.g. only `model_name`) fail validation at config load time.

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

`base_url` is not used for Anthropic.

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
