# Examples

Runnable demonstrations of OpenJury. Pick a track based on your goal.

## By track

| Example | Track | Prerequisites | Command |
|---------|-------|---------------|---------|
| [`hello_world/`](hello_world/) | Try it | None | `python score_existing.py` |
| [`basic_usage/`](basic_usage/) | Evaluate | `OPENAI_API_KEY`, agent on :8080 | `python basic_jury_run.py` |
| [`provider_configs/`](provider_configs/) | Config | Provider-specific keys | See provider README |
| [`batch_eval/`](batch_eval/) | Production | Keys + agent or mock | `python batch_run.py` |
| [`custom_scoring/`](custom_scoring/) | Production | Keys + agent | `python custom_scoring.py` |
| [`consistency_audit/`](consistency_audit/) | Production | Keys + agent | `python consistency_run.py` |
| [`resume_evaluation/`](resume_evaluation/) | Production | Keys + agent | `python resume_run.py` |
| [`web_server/`](web_server/) | Production | Keys + agent + Flask | `python web_integration.py` |

## Mock agent (local dev)

Most examples expect an agent at `localhost:8080`. Start the mock server:

```bash
python tools/mock_agent.py --port 8080
export AGENT_API_KEY=demo
```

See [tools/README.md](tools/README.md).

## Environment variables

| Variable | Used by |
|----------|---------|
| `OPENAI_API_KEY` | Most jury configs (`llm_provider`) |
| `OPENROUTER_API_KEY` | OpenRouter provider configs |
| `ANTHROPIC_API_KEY` | Mixed-provider configs |
| `AGENT_API_KEY` | Agent endpoint headers in `endpoints.json` |

Juror credentials belong in config JSON with `${VAR}` placeholders — not legacy env vars like `LLM_PROVIDER`.

## Next steps

- [docs/README.md](../docs/README.md) — reference documentation
- [recipes/README.md](../recipes/README.md) — task-oriented how-tos
- [notebooks/README.md](../notebooks/README.md) — Jupyter tutorials
