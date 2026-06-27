# Example Tools

## mock_agent.py

A tiny OpenAI-compatible HTTP server for local development. Most OpenJury examples expect an agent at `http://localhost:8080/v1/chat/completions`. This script satisfies that without deploying a real model.

```bash
# Terminal 1
python mock_agent.py --port 8080

# Terminal 2
export AGENT_API_KEY=demo OPENAI_API_KEY=sk-...
python ../basic_usage/basic_jury_run.py
```

The mock agent ignores the request body and always returns a deterministic password-reset response in `choices[0].message.content`.
