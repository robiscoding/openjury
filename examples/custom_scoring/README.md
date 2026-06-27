# Custom Scoring Function

OpenJury automatically computes eight canned metrics for every evaluation. This example shows how to register a domain-specific custom scoring function that appears as the `custom` field in `ScoredMetrics`.

## What you'll learn

- Registering a custom `ScoringFunction` via `ScoreAggregator.register()`
- Wiring `custom_scoring_function` in config JSON
- Reading `result.scored_metrics.custom` alongside canned metrics

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `OPENAI_API_KEY` or `OPENROUTER_API_KEY` | Per your config |
| Agent or mock | `python ../tools/mock_agent.py --port 8080` |

## When to use a custom function

The canned metrics cover most evaluation needs. A custom function is useful when:

- You have a **hard gate** — certain quality thresholds that must pass (e.g. any safety failure → score 0)
- You want a **business-specific composite** — e.g. weight recent juror opinions more heavily
- You need a **non-linear aggregation** — e.g. geometric mean, product of normalised scores

## How it works

```
juror_scores: List[JurorScore]
criteria:     List[CriterionConfig]
                     ↓
    your function returns a float (on the score_scale axis)
                     ↓
result.scored_metrics.custom = <your value>
```

Your function receives:
- `juror_scores` — one `JurorScore` per juror; each has `.criterion_scores: Dict[str, float]` and `.juror_weight: float`
- `criteria` — the `CriterionConfig` list; each has `.name`, `.weight`, `.rubric`

It must return a `float` on the same `score_scale` axis as everything else (e.g. 1–5).

## Example: safety gate

```python
from openjury import ScoreAggregator

def safety_gated(juror_scores, criteria):
    """Zero out composite if any juror rates safety below 2."""
    for js in juror_scores:
        if js.criterion_scores.get("safety", 5.0) < 2.0:
            return 0.0
    # otherwise fall back to weighted mean
    total_crit_w = sum(c.weight for c in criteria) or 1.0
    total_juror_w = sum(js.juror_weight for js in juror_scores) or 1.0
    return sum(
        sum(js.criterion_scores.get(c.name, 0.0) * js.juror_weight for js in juror_scores)
        / total_juror_w * c.weight
        for c in criteria
    ) / total_crit_w

ScoreAggregator.register("safety_gated", safety_gated)
```

## Wiring it in config.json

```json
{
  "custom_scoring_function": "safety_gated",
  ...
}
```

The string value must match the name you passed to `ScoreAggregator.register()`. You must register the function **before** calling `OpenJury.score_response()`.

## Cleanup

```python
ScoreAggregator.unregister("safety_gated")
```

Unregister after use to avoid collisions across test runs (the registry is class-level state).

## Files

| File | Purpose |
|------|---------|
| `config.json` | Jury config with `"custom_scoring_function": "safety_gated"` |
| `custom_scoring.py` | Registers the function, runs evaluation, reads `scored_metrics.custom` |

## Running

```bash
export OPENROUTER_API_KEY="..."
export AGENT_API_KEY="..."
python custom_scoring.py
```

## Output shape

```
result.scored_metrics.custom   → your value (or null if not registered)
result.scored_metrics.weighted_mean → normal composite (still always present)
```

The canned metrics are **always computed** regardless of whether a custom function is registered. Custom is additive, not a replacement.

## Next steps

- [recipes/custom-scoring-gate.md](../../recipes/custom-scoring-gate.md)
