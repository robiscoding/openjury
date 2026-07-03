# OpenJury Notebooks

Interactive Jupyter tutorials for exploring OpenJury.

## Setup

```bash
# From repo root
uv pip install -e ".[notebooks]"
jupyter lab notebooks/
```

Or with pip:

```bash
pip install openjury jupyter pandas
jupyter lab
```

## Notebooks

| Notebook | Description |
|----------|-------------|
| [00_quickstart.ipynb](00_quickstart.ipynb) | Install, offline demo, inspect `AgentEvalResult` |
| [01_config_and_providers.ipynb](01_config_and_providers.ipynb) | Provider resolution, valid/invalid overrides |
| [02_batch_and_metrics.ipynb](02_batch_and_metrics.ipynb) | Batch evaluation, `BatchRunSummary`, and metrics analysis |

Early cells run **offline** with fixture data. Final cells in each notebook optionally run live jurors when `OPENAI_API_KEY` is set.

## Related

- [examples/hello_world/](../examples/hello_world/) — same offline pattern as notebook 00
- [docs/README.md](../docs/README.md) — reference documentation
