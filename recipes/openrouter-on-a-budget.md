# OpenRouter on a Budget

One API key, many models — build a diverse jury cheaply via OpenRouter.

## Config

Copy [`examples/provider_configs/openrouter_multi_model.json`](../examples/provider_configs/openrouter_multi_model.json):

```json
{
  "llm_provider": {
    "provider": "openai_compatible",
    "model_name": "openai/gpt-4o-mini",
    "api_key": "${OPENROUTER_API_KEY}",
    "base_url": "https://openrouter.ai/api/v1"
  },
  "jurors": [
    {
      "name": "GPT Mini",
      "model_name": "openai/gpt-4o-mini",
      "api_key": "${OPENROUTER_API_KEY}",
      "provider": "openai_compatible",
      "base_url": "https://openrouter.ai/api/v1",
      "weight": 1.0
    },
    {
      "name": "Gemini Flash",
      "model_name": "google/gemini-2.0-flash-001",
      "api_key": "${OPENROUTER_API_KEY}",
      "provider": "openai_compatible",
      "base_url": "https://openrouter.ai/api/v1",
      "weight": 1.0
    }
  ]
}
```

Each juror with a different model needs a full override bundle.

## Environment

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

## Cost tips

- Use smaller models for jurors; reserve larger models for your agent under test
- Set low `temperature` (0.0–0.2) to reduce retries from parse failures
- Start with 2 jurors; add more only if `juror_agreement` is low

## Related

- [examples/provider_configs/](../examples/provider_configs/)
