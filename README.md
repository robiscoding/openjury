# OpenJury 🏛️

**A Python SDK for evaluating your agent's response quality using a configurable panel of LLM judges.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

---

## Overview

OpenJury is an agent evaluation framework. Point it at your agent's HTTP endpoint and it will:

1. Send a prompt to your agent and collect the response
2. Pass the response to a panel of LLM judges (jurors), each scoring it against your criteria
3. Return a composite quality score with a full statistical breakdown

The primary output is a single `composite_score` — a weighted mean of all juror scores across all criteria, plus eight additional canned metrics (median, harmonic mean, weakest link, juror agreement, and more). You can also register a custom scoring function for domain-specific logic.

### Why a jury instead of a single judge?

Relying on one LLM to evaluate outputs is common but fragile: it's expensive and prone to [intra-model bias](https://arxiv.org/abs/2404.13076). Research from Cohere [shows](https://arxiv.org/abs/2404.18796) that a panel of smaller, diverse models produces more reliable and less biased evaluations at lower cost.

OpenJury makes this practical: configure jurors declaratively in JSON, wire rubrics per criterion for consistent scoring, and get a structured result you can act on.

---

## Installation

**Requirements:** Python 3.11 or newer

```bash
pip install openjury
```

### From source

```bash
git clone https://github.com/robiscoding/openjury.git
cd openjury
pip install -e .
uv pip install -e ".[dev]"     # optional dev dependencies
```

---

## Choose your path

| Track | Goal | Time | API keys? |
|-------|------|------|-----------|
| **Try it** | See output shape, understand `AgentEvalResult` | 2 min | No |
| **Evaluate my agent** | Full fetch + score pipeline | 10 min | Yes |
| **Production integrate** | Batch, resume, custom scoring, CI | 30+ min | Yes |

### Try it (no agent, no keys)

```bash
pip install openjury
python examples/hello_world/score_existing.py
```

→ [examples/hello_world/](examples/hello_world/) · offline demo with sample output

### Evaluate my agent

```bash
# Terminal 1 — mock agent (or use your own endpoint)
python examples/tools/mock_agent.py --port 8080

# Terminal 2
export OPENAI_API_KEY="..." AGENT_API_KEY=demo
python examples/basic_usage/basic_jury_run.py
```

→ [examples/basic_usage/](examples/basic_usage/) · [docs/endpoint-config.md](docs/endpoint-config.md)

### Go deeper

- [docs/](docs/README.md) — architecture, config schema, composable API, CLI
- [recipes/](recipes/README.md) — task-oriented how-tos
- [notebooks/](notebooks/README.md) — interactive Jupyter walkthroughs
- [examples/](examples/README.md) — full examples index

---

## Quick Start

### 1. Create a jury config

Set a jury-level `llm_provider` for shared credentials. Jurors inherit it by default. Use `${ENV_VAR}` for secrets.

```json
{
  "name": "Customer Support Jury",
  "score_scale": 5,
  "llm_provider": {
    "provider": "openai_compatible",
    "model_name": "gpt-4o-mini",
    "api_key": "${OPENAI_API_KEY}"
  },
  "jurors": [
    { "name": "Support Expert", "system_prompt": "You are a senior support manager.", "weight": 2.0 },
    { "name": "Customer Perspective", "weight": 1.0 }
  ],
  "criteria": [
    {
      "name": "helpfulness",
      "description": "Does the response resolve the customer's issue?",
      "weight": 2.0,
      "rubric": {
        "1": "Ignores or misunderstands the question",
        "3": "Partially addresses the question",
        "5": "Directly and completely resolves the issue"
      }
    },
    {
      "name": "accuracy",
      "description": "Is the information factually correct?",
      "weight": 2.0,
      "rubric": {
        "1": "Contains factual errors",
        "3": "Mostly accurate with minor gaps",
        "5": "Completely accurate"
      }
    }
  ]
}
```

Full field reference: [docs/config-schema.md](docs/config-schema.md)

### 2. Run an evaluation

```python
from openjury import JuryConfig, OpenJury, ResultFormatter
from openjury.endpoint_fetcher import AgentEndpoint

jury = OpenJury(JuryConfig.from_json_file("jury_config.json"))

endpoint = AgentEndpoint(
    url="http://localhost:8080/v1/chat/completions",
    alias="my-agent",
    headers={"Authorization": "Bearer ${AGENT_API_KEY}"},
    request_body_template={
        "model": "my-model",
        "messages": [{"role": "user", "content": "{prompt}"}],
    },
)

result = jury.evaluate(prompt="How do I reset my password?", endpoint=endpoint)
print(ResultFormatter.format_result(result))
print(f"Score: {result.composite_score:.2f} / {result.score_scale}")
```

`score_response()` is a backward-compatible alias for `evaluate()`.

**CLI:**

```bash
openjury run \
  --config jury_config.json \
  --endpoints-config endpoints.json \
  --prompt "How do I reset my password?"
```

### 3. Read the output

```
╔══ Quality Evaluation  (scale: 1–5) ══
  composite_score:   3.87 / 5  (0.774 normalized)
  juror_agreement (0–1)        0.880   ← 1 = unanimous
  ...
```

- **`composite_score`** — headline quality number (`weighted_mean` from trial 1)
- **`juror_agreement`** — near 1.0 = high confidence; near 0 = contested
- **`weakest_link`** — flags a standout failure even when composite looks okay

---

## Key Features

- **Agent Evaluation** — score a single agent response per prompt
- **Structured Rubrics** — score anchors per criterion improve inter-juror reliability
- **Eight Canned Metrics** — weighted mean, median, harmonic mean, weakest link, juror agreement, and more
- **Custom Scoring** — register a Python function for domain-specific composite logic
- **Consistency Audit** — `num_trials > 1` measures response reliability
- **Batch Evaluation** — inline config datasets, JSONL/CSV files, or `evaluate_items()`
- **Parallel Processing** — concurrent jurors and batch items

---

## Examples

| Example | What it shows |
|---------|--------------|
| [`examples/hello_world/`](examples/hello_world/) | Offline demo — no agent, no API keys |
| [`examples/basic_usage/`](examples/basic_usage/) | Single prompt, full pipeline, reading `AgentEvalResult` |
| [`examples/provider_configs/`](examples/provider_configs/) | OpenAI, OpenRouter, Ollama, mixed providers |
| [`examples/batch_eval/`](examples/batch_eval/) | Inline/JSONL/CSV datasets, `batch-eval` CLI |
| [`examples/custom_scoring/`](examples/custom_scoring/) | `ScoreAggregator.register()`, safety-gate pattern |
| [`examples/consistency_audit/`](examples/consistency_audit/) | `num_trials > 1`, `ConsistencyResult.score_std` |
| [`examples/resume_evaluation/`](examples/resume_evaluation/) | Fetch/score split, crash recovery |
| [`examples/web_server/`](examples/web_server/) | Flask API wrapping evaluation |
| [`examples/tools/`](examples/tools/) | Mock agent for local development |

Full index: [examples/README.md](examples/README.md)

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ConfigurationError` for `${VAR}` | Export env vars before `OpenJury(...)`. See [provider-config.md](docs/provider-config.md) |
| Partial juror override `ValidationError` | Set all three: `model_name`, `api_key`, `provider`. See [config-schema.md](docs/config-schema.md) |
| `JurorException: missing criterion` | Juror JSON keys must match `criteria[].name` exactly |
| `EndpointFetchError` | Check URL, headers, `response_path`. See [endpoint-config.md](docs/endpoint-config.md) |
| Low `juror_agreement` | Add rubrics, lower juror temperature. See [recipes/design-rubrics.md](recipes/design-rubrics.md) |

---

## Documentation

| Resource | Description |
|----------|-------------|
| [docs/](docs/README.md) | Architecture, config schema, API, CLI |
| [recipes/](recipes/README.md) | Task-oriented cookbook |
| [notebooks/](notebooks/README.md) | Interactive tutorials |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup |

Advanced topics (moved from this README for brevity):

- [Composable API](docs/composable-api.md) — fetch/score split, batch, serialization
- [Batch evaluation](recipes/batch-eval-pipeline.md) — inline and JSONL/CSV datasets
- [Consistency audit](recipes/consistency-audit-before-ship.md) — `num_trials`
- [Custom scoring](recipes/custom-scoring-gate.md) — safety gates
- [Provider setup](docs/provider-config.md) — OpenAI, OpenRouter, Anthropic, Ollama

---

## Use Cases

- **Customer support agents** — score helpfulness, accuracy, and tone per response
- **Code review assistants** — evaluate correctness, readability, and security
- **Content generation** — assess clarity, tone, and factuality before publishing
- **Production monitoring** — track `composite_score` drift between model versions
- **Consistency testing** — run `num_trials=3` before shipping a prompt change

---

## License

Apache License 2.0. See [LICENSE](LICENSE).

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).
