# Kitchen Sink

A single reference configuration that demonstrates every major OpenJury feature in
one place. Use it as a template when building production jury configs.

## What this config includes

| Area | Features shown |
|------|----------------|
| **Jury settings** | `score_min`, `score_scale`, `num_trials` (consistency audit), `custom_scoring_function`, `require_explanation`, `max_retries` |
| **LLM provider** | Jury-level `llm_provider` with `${OPENAI_API_KEY}` interpolation |
| **Jurors** | Inherited provider, custom `system_prompt` / `temperature` / `weight`, and a full per-juror override (`model_name` + `api_key` + `provider`) |
| **Criteria** | Weighted criteria with exact and inclusive-range score rubrics |
| **Assertions** | Named policy registry with thresholds, required/optional checks, weights, and most assertion types |
| **Dataset** | Inline `dataset` rows with `id`, `input`, optional `ground_truth`, and `assertion_ids` (including multi-policy rows and juror-only rows) |

## Quick start (no API keys)

```bash
cd examples/kitchen_sink
python kitchen_sink_run.py
```

This loads and validates `config.json`, resolves assertion policies per dataset row,
and scores canned responses locally.

## Live evaluation

Start the mock agent (or point `endpoints.json` at your own service):

```bash
python ../tools/mock_agent.py --port 8080
export AGENT_API_KEY=demo
export OPENAI_API_KEY=sk-...
python kitchen_sink_run.py --live
python kitchen_sink_run.py --live --limit 1   # single row
```

Live mode registers the `support_gated` custom scoring function (referenced in
config), fetches agent responses, runs jurors with `num_trials=2`, and prints
full `AgentEvalResult` output including consistency metrics.

## CLI batch eval

The inline dataset can also be driven from the CLI:

```bash
python -m openjury.cli batch-eval \
  -c examples/kitchen_sink/config.json \
  -e examples/kitchen_sink/endpoints.json \
  -o /tmp/kitchen_sink_results.jsonl \
  --summary-output /tmp/kitchen_sink_summary.json
```

## Config map

### Assertion policies

- **`default`** — baseline checks applied only when a row references `assertion_ids: ["default"]`
- **`password_reset_contract`** — domain contract with `assertion_threshold` and `quality_threshold`
- **`order_status_contract`** — demonstrates `contains`, `starts_with`, `ends_with`, `contains_any`, `contains_all`, `regex`, `min_length`, `max_length`
- **`global_safety`** — cross-cutting safety checks combinable with other policies

Rows may reference multiple policies; checks are concatenated and the strictest
configured threshold wins.

### Rubric ranges

The `tone` criterion demonstrates inclusive range keys: `"0-2"`, `"3-4"`, and
the exact anchor `"5"`. A range-based rubric must cover every score in the
configured scale exactly once; overlaps, gaps, reversed ranges, and
out-of-scale bounds are rejected when the config loads.

### Dataset rows

| ID | Assertion policies | Notes |
|----|-------------------|-------|
| `password-reset-001` | `password_reset_contract`, `global_safety` | Multi-policy row with ground truth |
| `order-status-001` | `order_status_contract` | Strict formatting contract |
| `account-email-001` | *(none)* | Juror scoring only |
| `baseline-check-001` | `default` | Explicit default-policy reference |

## Related examples

For focused walkthroughs of individual features, see
[`assertions/`](../assertions/), [`batch_eval/`](../batch_eval/),
[`consistency_audit/`](../consistency_audit/), and
[`custom_scoring/`](../custom_scoring/).
