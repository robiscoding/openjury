# Basic Usage

Evaluate a single agent response to a single prompt, with a jury of LLM judges.

## What this example covers

- Configuring a jury with free-text criteria and structured rubrics
- Adding deterministic assertions beside model-graded criteria
- Calling `score_response()` to fetch from an agent endpoint and evaluate
- Reading the `AgentEvalResult` output — composite score, per-criterion breakdown, all metrics

## How OpenJury works

```
prompt → your agent endpoint → response text
                                     ↓
                         jury of LLM judges (jurors)
                         each juror scores per criterion
                                     ↓
                         ScoreAggregator computes metrics:
                         weighted_mean, mean, median,
                         min/max, harmonic_mean, weakest_link,
                         juror_agreement
                                     ↓
                         AgentEvalResult (composite_score + breakdown)
```

## Files

| File | Purpose |
|------|---------|
| `config.json` | Jury configuration — criteria with rubrics, juror models and weights |
| `basic_jury_run.py` | Python script that calls `score_response()` and prints results |

## Jury config format

```json
{
  "name": "My Jury",
  "score_scale": 5,
  "num_trials": 1,
  "llm_provider": {
    "provider": "openai_compatible",
    "model_name": "gpt-4o-mini",
    "api_key": "${OPENAI_API_KEY}"
  },
  "criteria": [
    {
      "name": "helpfulness",
      "description": "Does it resolve the user's request?",
      "weight": 2.0,
      "rubric": {
        "1": "Ignores the question entirely",
        "3": "Partially addresses it",
        "5": "Completely resolves the request"
      }
    }
  ],
  "jurors": [
    {
      "name": "Juror A",
      "weight": 1.0,
      "temperature": 0.1
    }
  ]
}
```

More real-world setups (OpenRouter, mixed providers, Ollama, etc.): [`../provider_configs/`](../provider_configs/)

**Key fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `llm_provider` | required* | Default provider bundle for jurors without a full override |
| `score_min` | `1` | Minimum integer score; set to `0` to enable zero |
| `score_scale` | `5` | Maximum integer score (global, not per-criterion) |
| `num_trials` | `1` | `1` = normal quality eval; `> 1` = consistency audit (see `consistency_audit/`) |
| `criteria[].rubric` | `null` | Exact anchors (`"1"`) or inclusive ranges (`"1-2"`). Strongly recommended — improves inter-juror reliability |
| `jurors[].weight` | `1.0` | Relative influence in `weighted_mean`; higher = more authoritative juror |
| `criteria[].weight` | `1.0` | Relative importance in composite score |
| `assertions` | `{}` | Named assertion-policy registry referenced by dataset rows |
| `dataset` | `[]` | Inline JSON rows with required `id`/`input` and optional `ground_truth`, `assertion_ids` |

JSON represents a CSV-style dataset as an array of row objects. Put reusable
contracts in the top-level `assertions` object, then select any number from a
row with `assertion_ids`. Assertions do not alter `composite_score`; inspect
`result.assertion_results` for their outcomes. See the
[`assertions` example](../assertions/) for all supported types.

\*Required unless every juror sets `model_name`, `api_key`, and `provider` together.

Rubric ranges use an inclusive hyphen convention:

```json
"rubric": {
  "1-2": "Incorrect or substantially incomplete",
  "3-4": "Mostly correct with limited omissions",
  "5": "Fully correct and complete"
}
```

When any range is used, the rubric must cover every integer from `score_min`
through `score_scale` exactly once. Exact-only rubrics may remain sparse (for
example, anchors at `"1"`, `"3"`, and `"5"`). Decimal scores and boundaries
are not supported.

## Agent endpoint format

Any HTTP endpoint works. The endpoint receives a POST with a body template, and returns JSON that OpenJury extracts a text field from.

```json
{
  "url": "http://localhost:8080/v1/chat/completions",
  "alias": "my-agent",
  "headers": { "Authorization": "Bearer ${MY_API_KEY}" },
  "request_body_template": {
    "model": "my-model",
    "messages": [{ "role": "user", "content": "{prompt}" }]
  },
  "response_path": "choices.0.message.content"
}
```

- Use `${ENV_VAR}` for credentials — never hardcode keys
- `{prompt}` is replaced with the prompt text at runtime
- `response_path` is a dot-notation path into the response JSON
- Set `"stream": true` for SSE streaming endpoints

## Understanding the output

```
composite_score:   3.87 / 5  (0.774 normalized)

Scoring Metrics:
  weighted_mean          3.870   ← primary composite; use this
  mean                   3.650   ← unweighted sanity check
  median                 3.900   ← outlier-resistant
  min_score              3.200   ← strictest juror's view
  max_score              4.300   ← most lenient juror's view
  harmonic_mean          3.710   ← penalises any criterion that scores low
  weakest_link           0.640   ← worst single criterion × its weight
  juror_agreement        0.880   ← 1 = unanimous; 0 = total disagreement

Criteria Breakdown:
  helpfulness (weight 2.0):   4.1  [agreement: 0.91  min: 3.5  max: 4.8]
  accuracy (weight 2.0):      3.6  [agreement: 0.84  min: 3.0  max: 4.2]
  tone (weight 1.0):          3.9  [agreement: 0.88  min: 3.5  max: 4.3]
```

- `composite_score` = `weighted_mean` from trial 1. This is the headline quality number.
- `juror_agreement` near 1.0 means jurors agree — high confidence in the score. Near 0 means the score is contested.
- `weakest_link` flags when one criterion is a standout failure even if the composite looks okay.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `OPENAI_API_KEY` | Juror LLM calls (see `config.json`) |
| `AGENT_API_KEY` | Agent endpoint auth (see `endpoints.json`) |
| Agent on `:8080` | Or run `python ../tools/mock_agent.py --port 8080` |

## Running

```bash
export OPENAI_API_KEY="sk-..."
export AGENT_URL="http://localhost:8080/v1/chat/completions"  # your agent

python basic_jury_run.py
```

Or via the CLI:

```bash
openjury run \
  --config config.json \
  --endpoints-config endpoints.json \
  --prompt "How do I reset my password?"
```

## Next steps

- [docs/endpoint-config.md](../../docs/endpoint-config.md) — endpoint field reference
- [recipes/design-rubrics.md](../../recipes/design-rubrics.md) — improve juror agreement
- [examples/consistency_audit/](../consistency_audit/) — reliability testing
