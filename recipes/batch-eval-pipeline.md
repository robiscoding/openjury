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
  --output results.jsonl
```

## Python API

```python
from openjury import EvaluationItem, ExecutionOptions

items = [
    EvaluationItem(prompt="Q1", item_id="case-1"),
    EvaluationItem(prompt="Q2", item_id="case-2", ground_truth="Expected answer"),
]
results = jury.evaluate_items(
    items, endpoint, options=ExecutionOptions(max_item_workers=3)
)

for r in results:
    if r.error:
        print(r.item.item_id, r.error)
    else:
        print(r.item.item_id, r.result.composite_score)
```

## Analyze results

```bash
openjury export-results --input results.jsonl --output summary.csv --format csv
```

## Runnable example

```bash
python examples/batch_eval/batch_run.py
```

## Related

- [docs/cli.md](../docs/cli.md)
- [examples/batch_eval/](../examples/batch_eval/)
