# Provider Config Examples

Copy-paste starting points for common real-world jury setups. Each file is a complete `JuryConfig` JSON you can pass to `JuryConfig.from_json_file()` or `openjury run --config`.

All configs use `${ENV_VAR}` for secrets — set the variables in your shell or CI before running.

## What you'll learn

- Provider-specific jury JSON for OpenAI, OpenRouter, Ollama, mixed providers, and gateways
- Per-juror override patterns
- Required environment variables per config

## Prerequisites

Export the env vars listed in the table below before loading configs or running evaluations.

## Which config to use

| File | When to use it |
|------|----------------|
| [`openai_direct.json`](openai_direct.json) | You have an OpenAI API key and want the simplest setup |
| [`openrouter.json`](openrouter.json) | One API key, access to many models via OpenRouter |
| [`openrouter_multi_model.json`](openrouter_multi_model.json) | Diverse jury — different models per juror, all via OpenRouter |
| [`mixed_providers.json`](mixed_providers.json) | GPT jurors on OpenAI + one native Claude juror (`pip install openjury[anthropic]`) |
| [`ollama_local.json`](ollama_local.json) | Local dev — jurors call Ollama on your machine |
| [`self_hosted_gateway.json`](self_hosted_gateway.json) | Corporate proxy (LiteLLM, vLLM, Azure-style gateway) in front of models |
| [`no_global_all_overrides.json`](no_global_all_overrides.json) | No shared `llm_provider` — every juror specifies its own provider bundle |

## Required environment variables

| Config | Variables |
|--------|-----------|
| `openai_direct.json` | `OPENAI_API_KEY` |
| `openrouter.json`, `openrouter_multi_model.json` | `OPENROUTER_API_KEY` |
| `mixed_providers.json` | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` |
| `ollama_local.json` | none (Ollama ignores the key locally) |
| `self_hosted_gateway.json` | `LITELLM_API_KEY` (rename to match your gateway) |
| `no_global_all_overrides.json` | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` |

## Override rules (reminder)

- **`llm_provider`** on the jury sets the default for all jurors that omit provider fields.
- To use a **different model or provider** for one juror, set all three flat fields on that juror: `model_name`, `api_key`, and `provider`. Optional `base_url` when needed.
- Partial overrides (e.g. only `model_name`) are invalid.

## Try one

```bash
export OPENAI_API_KEY="sk-..."
python -c "
from openjury import JuryConfig, OpenJury
cfg = JuryConfig.from_json_file('examples/provider_configs/openai_direct.json')
print(OpenJury(cfg).get_summary())
"
```

## Next steps

- [docs/provider-config.md](../../docs/provider-config.md)
- [recipes/mixed-provider-jury.md](../../recipes/mixed-provider-jury.md)
- [examples/basic_usage/](../basic_usage/)
