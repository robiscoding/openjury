# Batch Eval Pipeline

Run a dataset of prompts through the same jury and analyze results.

## Dataset format (JSONL)

```json
{"case_id": "case-1", "prompt": "How do I cancel my subscription?", "endpoints": [{"url": "http://localhost:8080/v1/chat/completions", "alias": "my-agent", "request_body_template": {"model": "my-model", "messages": [{"role": "user", "content": "{prompt}"}]}, "response_path": "choices.0.message.content"}]}
```

Or use a global endpoint:

```bash
openjury batch-eval \
  --config config.json \
  --input dataset.jsonl \
  --endpoints-config endpoints.json \
  --output results.jsonl \
  --summary-output summary.json \
  --workers 4
```

Each JSONL row includes structured fields (`status`, `error_code`, `error_stage`,
`evaluation_duration_ms`) plus enriched per-item data inside `eval` when scored.
The companion `summary.json` contains `BatchRunSummary` metrics for dashboard
headline cards: pass rate, score distribution, execution coverage, per-criterion
breakdown, and juror diagnostics.

## Python API

```python
from openjury import EvaluationItem, ExecutionOptions

items = [
    EvaluationItem(prompt="Q1", item_id="case-1"),
    EvaluationItem(prompt="Q2", item_id="case-2", ground_truth="Expected answer"),
]
batch = jury.evaluate_items_with_summary(
    items, endpoint, options=ExecutionOptions(max_item_workers=3)
)

print(batch.summary.pass_rate, batch.summary.mean_composite_score)
print(batch.summary.coverage.successfully_scored, "of", batch.summary.coverage.dataset_items)

for item_result in batch.items:
    if item_result.status.value != "scored":
        print(item_result.item.item_id, item_result.error_code, item_result.error_stage)
    else:
        assert item_result.result is not None
        print(
            item_result.item.item_id,
            item_result.result.composite_score,
            item_result.result.contested,
        )
```

You can also aggregate stored rows later:

```python
from openjury import aggregate_batch_results

summary = aggregate_batch_results(item_results, score_scale=jury.config.score_scale)
```

## Analyze results

```bash
openjury export-results \
  --input results.jsonl \
  --output summary.csv \
  --format csv \
  --summary-output summary.json
```

## Runnable example

```bash
python examples/batch_eval/batch_run.py \
  --config examples/basic_usage/config.json \
  --dataset examples/batch_eval/sample_dataset.jsonl \
  --endpoints-config examples/basic_usage/endpoints.json \
  --output /tmp/results.jsonl \
  --summary-output /tmp/summary.json
```

## Related

- [docs/cli.md](../docs/cli.md)
- [examples/batch_eval/](../examples/batch_eval/)
- [notebooks/02_batch_and_metrics.ipynb](../notebooks/02_batch_and_metrics.ipynb)
