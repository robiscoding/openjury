# Custom Scoring Gate

Register a Python function to enforce domain rules on the composite score — e.g. zero out if safety fails.

## Register a scorer

```python
from openjury import ScoreAggregator

def safety_gated(juror_scores, criteria):
    for js in juror_scores:
        if js.criterion_scores.get("safety", 5.0) < 2.0:
            return 0.0
    total_crit_w = sum(c.weight for c in criteria) or 1.0
    total_juror_w = sum(js.juror_weight for js in juror_scores) or 1.0
    return sum(
        sum(js.criterion_scores.get(c.name, 0.0) * js.juror_weight for js in juror_scores)
        / total_juror_w * c.weight
        for c in criteria
    ) / total_crit_w

ScoreAggregator.register("safety_gated", safety_gated)
```

Or pass at init (preferred):

```python
jury = OpenJury(config, custom_scoring_functions={"safety_gated": safety_gated})
```

## Reference in config

```json
{ "custom_scoring_function": "safety_gated" }
```

## Read result

```python
print(result.scored_metrics.custom)  # your gated score
print(result.composite_score)         # standard weighted_mean (unchanged)
```

## Runnable example

```bash
python examples/custom_scoring/custom_scoring.py
```

## Related

- [examples/custom_scoring/](../examples/custom_scoring/)
