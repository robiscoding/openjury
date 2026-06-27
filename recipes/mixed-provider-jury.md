# Mixed Provider Jury

Combine OpenAI-compatible and Anthropic jurors for a more diverse, less biased panel.

## Install

```bash
pip install openjury[anthropic]
```

## Config

Use [`examples/provider_configs/mixed_providers.json`](../examples/provider_configs/mixed_providers.json):

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

## Environment

```bash
export OPENAI_API_KEY="..." ANTHROPIC_API_KEY="..."
```

## Rules

- Per-juror override requires **all three**: `model_name`, `api_key`, `provider`
- No field merging from the global `llm_provider`
- `base_url` only applies to `openai_compatible`

## Related

- [docs/provider-config.md](../docs/provider-config.md)
