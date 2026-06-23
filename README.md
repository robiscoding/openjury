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

## Key Features

- **Agent Evaluation:** Score a single agent response per prompt
- **Structured Rubrics:** Explicit score anchors per criterion dramatically improve inter-juror reliability
- **Eight Canned Metrics:** `weighted_mean`, `mean`, `median`, `min/max`, `harmonic_mean`, `weakest_link`, `juror_agreement`
- **Custom Scoring:** Register a custom scorer (python function) for domain-specific composite logic
- **Consistency Audit:** Run `num_trials > 1` to measure how reliably your agent responds to the same prompt
- **Endpoint Fetching:** OpenJury integrates seamlessly as it calls your agent via your http generate endpoint
- **Batch Evaluation:** Run a JSONL or CSV dataset of prompts through the same jury
- **Parallel Processing:** Jurors run concurrently; batch cases are independent
- **CLI:** `openjury run` and `openjury batch-eval` for script-free operation

---

## Installation

**Requirements:** Python 3.11 or newer

```bash
pip install openjury
```

### From Source (for development/contribution)

```bash
git clone https://github.com/robiscoding/openjury.git
cd openjury
pip install -e .
uv pip install -e ".[dev]"     # (optional) dev dependencies
```

---

## Quick Start

### 1. Set environment variables

Juror models run via [OpenRouter](https://openrouter.ai) by default:

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

Or use OpenAI directly:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY="sk-..."
```

### 2. Create a jury config

```json
{
  "name": "Customer Support Jury",
  "score_scale": 5,
  "jurors": [
    {
      "name": "Support Expert",
      "model_name": "qwen/qwen3-4b:free",
      "system_prompt": "You are a senior customer support manager.",
      "weight": 2.0,
      "temperature": 0.1
    },
    {
      "name": "Customer Perspective",
      "model_name": "mistralai/devstral-small-2505:free",
      "weight": 1.0,
      "temperature": 0.3
    }
  ],
  "criteria": [
    {
      "name": "helpfulness",
      "description": "Does the response resolve the customer's issue?",
      "weight": 2.0,
      "rubric": {
        "1": "Ignores or misunderstands the question",
        "3": "Partially addresses the question but misses key information",
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

**Key fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `score_scale` | `5` | Global score scale — all criteria scored 1–N |
| `num_trials` | `1` | `1` = quality eval; `> 1` = consistency audit |
| `criteria[].rubric` | `null` | Score anchors per level — strongly recommended |
| `jurors[].weight` | `1.0` | Relative influence in `weighted_mean` |

### 3. Define your agent endpoint

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

Use `${ENV_VAR}` for credentials (never hardcode keys). `{prompt}` is replaced with the prompt text at runtime.

### 4. Run an evaluation

**Python:**

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

result = jury.score_response(
    prompt="How do I reset my password?",
    endpoint=endpoint,
)

print(ResultFormatter.format_result(result))
print(f"Score: {result.composite_score:.2f} / {result.score_scale}")
```

**CLI:**

```bash
export AGENT_API_KEY="..."
openjury run \
  --config jury_config.json \
  --endpoints-config endpoints.json \
  --prompt "How do I reset my password?"
```

### 5. Read the output

```
╔══ Quality Evaluation  (scale: 1–5) ══
  Jury:              Customer Support Jury
  Endpoint:          my-agent

  composite_score:   3.87 / 5  (0.774 normalized)

  Scoring Metrics:
    weighted_mean                3.870   ← primary composite; use this
    mean                         3.650
    median                       3.900
    min_score                    3.200   ← strictest juror's view
    max_score                    4.300   ← most lenient juror's view
    harmonic_mean                3.710   ← penalises low criterion scores
    weakest_link                 0.640   ← worst criterion × its weight
    juror_agreement (0–1)        0.880   ← 1 = unanimous

  Criteria Breakdown:
    helpfulness (weight 2.0):  4.10  [agreement: 0.91  min: 3.5  max: 4.8]
    accuracy (weight 2.0):     3.60  [agreement: 0.84  min: 3.0  max: 4.2]
╚══
```

- **`composite_score`** is the `weighted_mean` from trial 1 — this is the headline quality number
- **`juror_agreement`** near 1.0 means high confidence in the score; near 0 means contested
- **`weakest_link`** flags a standout failure even when the composite looks okay

---

## Batch Evaluation

Run a JSONL or CSV dataset of prompts through the same jury:

```bash
openjury batch-eval \
  --config jury_config.json \
  --input dataset.jsonl \
  --output results.jsonl
```

Each case in `dataset.jsonl`:

```json
{
  "case_id": "case-1",
  "prompt": "How do I cancel my subscription?",
  "endpoints": [
    {
      "url": "http://localhost:8080/v1/chat/completions",
      "alias": "my-agent",
      "request_body_template": {
        "model": "my-model",
        "messages": [{"role": "user", "content": "{prompt}"}]
      },
      "response_path": "choices.0.message.content"
    }
  ]
}
```

Or supply a global endpoint fallback for all cases:

```bash
openjury batch-eval \
  --config jury_config.json \
  --input dataset.jsonl \
  --endpoints-config endpoints.json \
  --output results.jsonl
```

---

## Consistency Audit

Set `num_trials > 1` to measure how reliably your agent produces similar-quality responses to the same prompt. OpenJury calls the endpoint N times, evaluates each independently, and reports the standard deviation across trials.

```json
{ "num_trials": 3, "score_scale": 5 }
```

```
  ── Consistency Audit ──
  trials:      3
  score_std:   0.08  (mean: 3.91  min: 3.82  max: 3.99)
  trial scores: [3.99, 3.82, 3.91]
  low variance (std=0.08) — agent responds consistently
```

| `score_std` | Meaning |
|-------------|---------|
| < 0.1 | Low — agent is very consistent |
| 0.1–0.3 | Moderate — consider reviewing temperature |
| ≥ 0.3 | High — agent is unpredictable |

The `composite_score` always comes from trial 1. Trials 2–N only populate `consistency_result` — they are not averaged into quality, since users each experience one response, not a mean.

---

## Custom Scoring

Register a Python function for domain-specific composite logic. It receives all juror scores and criteria, and must return a `float` on the `score_scale` axis:

```python
from openjury import ScoreAggregator

def safety_gated(juror_scores, criteria):
    """Zero out composite if any juror rates safety below 2."""
    for js in juror_scores:
        if js.criterion_scores.get("safety", 5.0) < 2.0:
            return 0.0
    # fall back to weighted mean
    total_crit_w = sum(c.weight for c in criteria) or 1.0
    total_juror_w = sum(js.juror_weight for js in juror_scores) or 1.0
    return sum(
        sum(js.criterion_scores.get(c.name, 0.0) * js.juror_weight for js in juror_scores)
        / total_juror_w * c.weight
        for c in criteria
    ) / total_crit_w

ScoreAggregator.register("safety_gated", safety_gated)
```

Reference it in `jury_config.json`:

```json
{ "custom_scoring_function": "safety_gated" }
```

The result appears as `result.scored_metrics.custom`. Canned metrics are always computed regardless.

---

## Endpoint Configuration Reference

| Field | Default | Description |
|-------|---------|-------------|
| `url` | required | Any URL — `http://localhost:…`, `https://…` |
| `alias` | `url` | Display name in results |
| `headers` | `{}` | HTTP headers; use `${ENV_VAR}` for credentials |
| `request_body_template` | OpenAI chat shape | Any JSON; `{prompt}` is substituted at runtime |
| `stream` | `false` | `true` = SSE streaming, accumulated before evaluation |
| `response_path` | `choices.0.message.content` | Dot-notation path into the response JSON |
| `timeout_s` | `60.0` | Per-request timeout in seconds |

**Custom request body (non-OpenAI agent):**
```json
{
  "url": "http://localhost:8080/generate",
  "alias": "local-agent",
  "request_body_template": { "prompt": "{prompt}" },
  "response_path": "text"
}
```

**SSE streaming:**
```json
{
  "url": "https://your-api.example.com/v1/chat/completions",
  "alias": "streaming-model",
  "headers": { "Authorization": "Bearer ${MY_API_KEY}" },
  "stream": true
}
```

When `stream: true` and `response_path` is not set, OpenJury automatically uses the SSE per-chunk path (`choices.0.delta.content`).

---

## Examples

| Example | What it shows |
|---------|--------------|
| [`examples/basic_usage/`](examples/basic_usage/) | Single prompt, `score_response()`, reading `AgentEvalResult` |
| [`examples/batch_eval/`](examples/batch_eval/) | JSONL/CSV dataset, `batch-eval` CLI, output analysis |
| [`examples/custom_scoring/`](examples/custom_scoring/) | `ScoreAggregator.register()`, safety-gate pattern |
| [`examples/consistency_audit/`](examples/consistency_audit/) | `num_trials > 1`, reading `ConsistencyResult.score_std` |
| [`examples/web_server/`](examples/web_server/) | Flask API wrapping `score_response()` |

---

## Use Cases

- **Customer support agents** — score helpfulness, accuracy, and tone per response; monitor quality over time
- **Code review assistants** — evaluate correctness, readability, and security criteria with rubric anchors
- **Content generation** — assess clarity, tone, and factuality before publishing
- **Production monitoring** — track `composite_score` drift between model versions or prompt changes
- **Consistency testing** — before shipping a prompt, run `num_trials=3` to verify stable output quality

---

## License

OpenJury is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.
