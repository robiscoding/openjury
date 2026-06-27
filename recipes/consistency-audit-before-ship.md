# Consistency Audit Before Ship

Verify your agent produces stable quality before deploying a prompt or model change.

## Config

```json
{
  "score_scale": 5,
  "num_trials": 3
}
```

OpenJury calls your agent 3 times, scores each independently, and reports variance.

## Interpret results

```python
result = jury.evaluate(prompt, endpoint)

print(result.composite_score)  # quality — always trial 1
if result.consistency_result:
    cr = result.consistency_result
    print(f"std={cr.score_std:.2f}  scores={cr.trial_composite_scores}")
    print(cr.interpretation)
```

| `score_std` | Meaning |
|-------------|---------|
| < 0.1 | Very consistent |
| 0.1–0.3 | Moderate — review temperature |
| ≥ 0.3 | Unpredictable — investigate before shipping |

**Important:** `composite_score` is trial 1 only. Do not use `consistency_result.score_mean` as the quality score.

## CLI

```bash
openjury run \
  --config config.json \
  --endpoints-config endpoints.json \
  --prompt "Test prompt" \
  --consistency-trials 2
```

Sets total trials to `1 + 2 = 3`.

## Runnable example

```bash
python examples/consistency_audit/consistency_run.py
```

## Related

- [examples/consistency_audit/](../examples/consistency_audit/)
