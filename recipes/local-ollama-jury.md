# Local Ollama Jury

Run jurors against local Ollama models — zero cloud cost for development.

## Prerequisites

```bash
ollama serve
ollama pull llama3.2
```

## Config

Use [`examples/provider_configs/ollama_local.json`](../examples/provider_configs/ollama_local.json):

```json
{
  "llm_provider": {
    "provider": "openai_compatible",
    "model_name": "llama3.2",
    "api_key": "ollama",
    "base_url": "http://localhost:11434/v1"
  },
  "jurors": [
    { "name": "Local Juror A", "weight": 1.0 },
    { "name": "Local Juror B", "weight": 1.0 }
  ]
}
```

No API key env vars required — Ollama ignores the placeholder key locally.

## Smoke test

```python
from openjury import JuryConfig, OpenJury

cfg = JuryConfig.from_json_file("examples/provider_configs/ollama_local.json")
print(OpenJury(cfg).get_summary())
```

## Caveats

- Local models may produce less reliable JSON; increase `max_retries` if needed
- Use cloud jurors for production-quality calibration

## Related

- [docs/provider-config.md](../docs/provider-config.md)
