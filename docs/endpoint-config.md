# Endpoint Configuration

OpenJury calls your agent via HTTP before scoring. Configure endpoints in Python or JSON.

## Python

```python
from openjury.endpoint_fetcher import AgentEndpoint

endpoint = AgentEndpoint(
    url="http://localhost:8080/v1/chat/completions",
    alias="my-agent",
    headers={"Authorization": "Bearer ${AGENT_API_KEY}"},
    request_body_template={
        "model": "my-model",
        "messages": [{"role": "user", "content": "{prompt}"}],
    },
    response_path="choices.0.message.content",
    timeout_s=60.0,
)
```

## JSON file

```json
[
  {
    "url": "http://localhost:8080/v1/chat/completions",
    "alias": "my-agent",
    "headers": { "Authorization": "Bearer ${AGENT_API_KEY}" },
    "request_body_template": {
      "model": "my-model",
      "messages": [{ "role": "user", "content": "{prompt}" }]
    },
    "response_path": "choices.0.message.content"
  }
]
```

Load with `load_endpoints_file("endpoints.json")[0]`.

## Field reference

| Field | Default | Description |
|-------|---------|-------------|
| `url` | required | Agent URL (local or remote) |
| `alias` | `url` | Display name in results |
| `headers` | `{}` | HTTP headers; `${ENV_VAR}` supported |
| `request_body_template` | OpenAI chat shape | JSON body; `{prompt}` substituted at runtime |
| `response_path` | `choices.0.message.content` | Dot-notation path into response JSON |
| `stream` | `false` | SSE streaming; accumulates before scoring |
| `timeout_s` | `60.0` | Per-request timeout |

## Non-OpenAI agents

```json
{
  "url": "http://localhost:8080/generate",
  "alias": "local-agent",
  "request_body_template": { "prompt": "{prompt}" },
  "response_path": "text"
}
```

## SSE streaming

```json
{
  "url": "https://api.example.com/v1/chat/completions",
  "stream": true,
  "headers": { "Authorization": "Bearer ${MY_API_KEY}" }
}
```

When `stream: true` and `response_path` is default, OpenJury uses `choices.0.delta.content` for per-chunk SSE.

## Local development

Use the mock agent for examples:

```bash
python examples/tools/mock_agent.py --port 8080
export AGENT_API_KEY=demo
```

## Error behavior

Endpoint failures raise `EndpointFetchError` and abort evaluation. There are no automatic retries — rerun on transient failures.

See [architecture.md](architecture.md#error-semantics).
