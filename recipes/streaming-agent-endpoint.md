# Streaming Agent Endpoint

Configure OpenJury to consume SSE streaming responses from your agent.

## Config

```json
{
  "url": "https://your-api.example.com/v1/chat/completions",
  "alias": "streaming-agent",
  "headers": { "Authorization": "Bearer ${AGENT_API_KEY}" },
  "stream": true,
  "request_body_template": {
    "model": "my-model",
    "messages": [{ "role": "user", "content": "{prompt}" }],
    "stream": true
  }
}
```

## Default behavior

When `stream: true` and `response_path` is default (`choices.0.message.content`), OpenJury automatically uses the SSE delta path: `choices.0.delta.content`.

## Custom streaming shape

Override `response_path` for non-OpenAI APIs:

```json
{
  "stream": true,
  "response_path": "delta.text"
}
```

## Python

```python
from openjury.endpoint_fetcher import AgentEndpoint

endpoint = AgentEndpoint(
    url="https://api.example.com/v1/chat/completions",
    alias="stream-agent",
    stream=True,
    headers={"Authorization": "Bearer ${AGENT_API_KEY}"},
)
```

## Related

- [docs/endpoint-config.md](../docs/endpoint-config.md)
