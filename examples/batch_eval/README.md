# Batch Evaluation

Run many prompts through the same jury configuration, recording an `AgentEvalResult` per prompt. Results are written as JSONL — one object per line.

## What you'll learn

- JSONL/CSV dataset formats for batch evaluation
- CLI `batch-eval` and Python `evaluate_items()` patterns
- Analyzing JSONL output with pandas

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `OPENAI_API_KEY` | Juror LLM calls |
| Agent or mock | `python ../tools/mock_agent.py --port 8080` |

## Dataset formats

### JSONL (recommended)

Each non-empty line is one JSON object:

| Field | Required | Description |
|-------|----------|-------------|
| `case_id` | yes | Stable identifier for joins and reruns |
| `prompt` | yes | Prompt sent to the agent and evaluated |
| `endpoints` | no | List of endpoint specs. The **first** entry is used. If omitted, a global `--endpoints-config` must be supplied at run time |
| `exemplars` | no | Calibration examples + per-case rules (see below) |
| `metadata` | no | Arbitrary JSON for your bookkeeping (not sent to jurors) |

**`exemplars` object** (all parts optional):

```json
{
  "adequate":   [{ "text": "...", "reason": "..." }],
  "inadequate": [{ "text": "...", "reason": "..." }],
  "rules": "Extra instructions for this case only"
}
```

Exemplars are turned into calibration text injected into the juror evaluation prompt, helping jurors understand what a good vs. bad response looks like for this specific case.

### CSV

Header row must include `case_id`, `prompt`, `endpoints_json`.

Optional columns: `exemplars_json`, `metadata_json`.

## Endpoint precedence

1. **Case-level `endpoints`** — first entry is used
2. **Global `--endpoints-config`** — fallback when a case has no inline endpoints

If neither is present, the case fails with a clear error.

## Output JSONL

Each output line contains:

| Field | Description |
|-------|-------------|
| `case_id` | From the dataset |
| `run_metadata.jury_name` | From the jury config |
| `run_metadata.config_path` | Absolute path to the jury JSON used |
| `error` | `null` on success; error message string on failure |
| `eval` | `null` on failure; `AgentEvalResult` fields on success |
| `eval.composite_score` | Primary quality score (weighted_mean, trial 1) |
| `eval.normalized_composite_score` | `composite_score / score_scale` (0–1) |
| `eval.score_scale` | Scale used (e.g. `5`) |
| `eval.scored_metrics` | All canned metrics (weighted_mean, median, weakest_link, …) |
| `eval.criteria_evaluations` | Per-criterion breakdown with per-juror explanations |
| `eval.consistency_result` | `null` unless `num_trials > 1` in the jury config |

## Running

### CLI

```bash
export MY_AGENT_KEY="..."

# With per-case endpoints in the dataset
openjury batch-eval \
  --config ../basic_usage/config.json \
  --input sample_dataset.jsonl \
  --output results.jsonl \
  --verbose

# With a global endpoint fallback for all cases
openjury batch-eval \
  --config ../basic_usage/config.json \
  --input sample_dataset.jsonl \
  --endpoints-config endpoints.json \
  --output results.jsonl
```

### Python script

```bash
python batch_run.py \
  --config ../basic_usage/config.json \
  --dataset sample_dataset.jsonl \
  --output out.jsonl
```

## Jury config

Use the same `JuryConfig` JSON as in `basic_usage/`. Key fields:

- `score_scale` — global score scale (default `5`)
- `num_trials` — set to `> 1` to add a consistency audit for every case (expensive)
- `criteria[].rubric` — recommended for batch evals where consistent juror scoring matters most

## Analysing output

The output JSONL is easy to load into pandas or any analytics tool:

```python
import json, pandas as pd

rows = [json.loads(l) for l in open("results.jsonl")]
df = pd.json_normalize([
    {
        "case_id": r["case_id"],
        "error": r["error"],
        "composite_score": (r.get("eval") or {}).get("composite_score"),
        "juror_agreement": (r.get("eval") or {}).get("scored_metrics", {}).get("juror_agreement"),
    }
    for r in rows
])
print(df.sort_values("composite_score"))
```

## Endpoint configuration reference

See [endpoint fields in the `AgentEndpoint` model](../../src/openjury/endpoint_fetcher.py):

| Field | Default | Description |
|-------|---------|-------------|
| `url` | required | Any URL — localhost, https, etc. |
| `alias` | `url` | Display name in results |
| `headers` | `{}` | HTTP headers; use `${ENV_VAR}` for credentials |
| `request_body_template` | OpenAI shape | Any JSON; use `{prompt}` in string values |
| `stream` | `false` | `true` = SSE streaming, accumulated before evaluation |
| `response_path` | `choices.0.message.content` | Dot-notation path into response JSON |
| `timeout_s` | `60.0` | Per-request timeout |

## Next steps

- [recipes/batch-eval-pipeline.md](../../recipes/batch-eval-pipeline.md)
- [docs/cli.md](../../docs/cli.md)
