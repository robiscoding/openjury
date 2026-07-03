# Composable Evaluation API

For batch runners, crash recovery, and hosted workers, OpenJury splits fetching and scoring.

## Full evaluation

```python
from openjury import JuryConfig, OpenJury, ResultFormatter
from openjury.endpoint_fetcher import AgentEndpoint

jury = OpenJury(JuryConfig.from_json_file("config.json"))
endpoint = AgentEndpoint(url="https://agent.example/v1/chat/completions", alias="agent")

result = jury.evaluate("How do I reset my password?", endpoint)
# score_response() is an alias for evaluate()
print(ResultFormatter.format_result(result))
```

## Fetch only

```python
from openjury import ExecutionOptions, fetch_agent_response

options = ExecutionOptions(idempotency_key="run-123")
fetch = fetch_agent_response(endpoint, "Question?", options=options)
text = fetch.response.content
# persist text to storage...
```

## Score existing response

Skip the agent call when you already have the text:

```python
from openjury import AgentResponse

result = jury.score_existing_response(
    prompt="Question?",
    agent_response=AgentResponse(content=persisted_text),
)
print(result.composite_score)
```

### Partial juror resume

Returns `ScoringResult` when you need failure details:

```python
scoring = jury.score_existing_response(
    prompt="Question?",
    agent_response=AgentResponse(content=persisted_text),
    jurors_to_run=["juror-key-a"],  # resume only failed jurors
    raise_if_all_jurors_failed=False,
)
if scoring.result:
    print(scoring.result.composite_score)
else:
    print(scoring.juror_failures)
```

## Batch evaluation

```python
from openjury import EvaluationItem, ExecutionOptions

items = [
    EvaluationItem(prompt="Q1", item_id="item-1", ground_truth="A1"),
    EvaluationItem(prompt="Q2", item_id="item-2"),
]
options = ExecutionOptions(max_item_workers=3, max_juror_workers=5)
results = jury.evaluate_items(items, endpoint, options=options)

for item_result in results:
    if item_result.status.value != "scored":
        print(item_result.error_code, item_result.error_stage, item_result.error_message)
    else:
        result = item_result.result
        assert result is not None
        print(
            item_result.item.item_id,
            result.composite_score,
            result.passed,
            result.contested,
        )
```

For run-level dashboard metrics in one call:

```python
batch = jury.evaluate_items_with_summary(items, endpoint, options=options)
print(batch.summary.pass_rate)
print(batch.summary.score_distribution.p10)
print(batch.summary.jurors[0].scoring_tendency)
```

Or aggregate stored `ItemEvalResult` rows later:

```python
from openjury import aggregate_batch_results

summary = aggregate_batch_results(results, score_scale=jury.config.score_scale)
```

Per-item results now include `quality_passed`, `assertion_threshold_met`,
`quality_threshold`, `contested`, `lowest_criterion`, `evaluation_duration_ms`,
and juror `latency_ms` on each `JurorScore`.

`score_batch()` is a sequential, fail-fast wrapper over `evaluate_items` with `max_item_workers=1`.

## ExecutionOptions

| Option | Default | Description |
|--------|---------|-------------|
| `max_juror_workers` | 5 | Parallel juror calls |
| `max_item_workers` | 1 | Parallel batch items |
| `max_outbound_requests` | 10 | Global HTTP/LLM concurrency cap |
| `idempotency_key` | `null` | Passed to fetch metadata |
| `ground_truth` | `null` | Optional reference answer for jurors |
| `contested_threshold` | `null` | Override jury config contested threshold (default 0.6) |
| `cancel_event` | `null` | `threading.Event` for cancellation |
| `on_progress` | `null` | Callback for `ProgressEvent` updates (includes `timestamp_ms`) |

## Serialization

```python
from openjury import serialize_eval_result
import json

payload = serialize_eval_result(result)
json.dumps(payload, indent=2)
```

Use for persisting results, API responses, and JSONL batch output.

## Crash recovery pattern

1. `fetch_agent_response()` → persist response text
2. On failure, retry `score_existing_response()` with `jurors_to_run` for partial work

See [recipes/crash-recovery-resume.md](../recipes/crash-recovery-resume.md) and [examples/resume_evaluation/](../examples/resume_evaluation/).
