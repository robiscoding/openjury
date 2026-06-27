# OpenJury Documentation

In-repo reference for SDK users and contributors. Start with the track that matches your goal.

## Reading order

### New to OpenJury

1. [Hello world example](../examples/hello_world/) — offline demo, no API keys
2. [Basic usage example](../examples/basic_usage/) — full fetch + score pipeline
3. [Architecture](architecture.md) — how evaluation flows end-to-end
4. [Config schema](config-schema.md) — jury JSON reference

### Integrating in production

1. [Composable API](composable-api.md) — fetch/score split, batch, serialization
2. [Endpoint configuration](endpoint-config.md) — agent HTTP setup
3. [Provider configuration](provider-config.md) — juror LLM credentials
4. [CLI reference](cli.md) — script-free operation
5. [Recipes](../recipes/README.md) — task-oriented how-tos

### Interactive exploration

- [Notebooks](../notebooks/README.md) — Jupyter walkthroughs

## Reference

| Doc | Contents |
|-----|----------|
| [architecture.md](architecture.md) | Evaluation flow, concurrency, error semantics |
| [config-schema.md](config-schema.md) | `JuryConfig` JSON fields, valid/invalid examples |
| [config.schema.json](config.schema.json) | Machine-readable JSON Schema (generated) |
| [composable-api.md](composable-api.md) | `evaluate`, `score_existing_response`, `evaluate_items` |
| [endpoint-config.md](endpoint-config.md) | Agent endpoint fields, streaming, custom shapes |
| [provider-config.md](provider-config.md) | LLM provider resolution, per-juror overrides |
| [cli.md](cli.md) | All CLI commands with examples |

## Examples index

See [examples/README.md](../examples/README.md) for runnable examples with prerequisites.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup. Agent-oriented repo guide: [AGENTS.md](../AGENTS.md).
