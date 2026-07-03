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
| **Assertions** | `global_assertions`, reusable `assertion_profiles`, `assertion_policy` defaults, template variables |
| **Dataset** | Inline `dataset` rows with `id`, `input`, optional `ground_truth`, `assertion_profile_ids`, and `variables` |

## Quick start (no API keys)

```bash
cd examples/kitchen_sink
python kitchen_sink_run.py
```

This loads and validates `config.json`, resolves assertions per dataset row,
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

### Assertion layers

Resolution order for every item:

1. **`global_assertions`** — applied automatically (empty response, no stack traces, etc.)
2. **Selected `assertion_profile_ids`** — task-specific contracts
3. **Inline `dataset[].assertions`** — optional per-row supplements

Default pass thresholds live in **`assertion_policy`**. A single selected profile
may override them; per-row overrides win over both.

### Assertion profiles

- **`password_reset_contract`** — domain contract with profile-level thresholds
- **`order_status_contract`** — demonstrates string/list assertion types plus `{{order_number}}` / `{{order_path}}` template variables

### Rubric ranges

The `tone` criterion demonstrates exact score anchors at `0`, `1`, `3`, and `5`.

### Dataset rows

| ID | Profiles | Notes |
|----|----------|-------|
| `password-reset-001` | `password_reset_contract` | Globals + profile checks |
| `order-status-001` | `order_status_contract` | Template variables for order-specific values |
| `account-email-001` | *(none)* | Global assertions only |
| `baseline-check-001` | *(none)* | Global assertions only |

## Related examples

For focused walkthroughs of individual features, see
[`assertions/`](../assertions/), [`batch_eval/`](../batch_eval/),
[`consistency_audit/`](../consistency_audit/), and
[`custom_scoring/`](../custom_scoring/).
