# Design Rubrics

Structured rubrics dramatically improve `juror_agreement` across diverse juror models.

## Pattern

Key rubric levels by exact score strings (`"1"`, `"3"`, `"5"`) or inclusive
range strings (`"1-2"`, `"3-4"`):

```json
{
  "name": "helpfulness",
  "description": "Does the response resolve the user's request?",
  "weight": 2.0,
  "rubric": {
    "1": "Ignores or misunderstands the question entirely",
    "3": "Partially addresses the question but misses key information",
    "5": "Directly and completely resolves the issue"
  }
}
```

Use hyphens rather than commas: commas conventionally describe a set, while a
hyphen clearly communicates an interval. If any range is present, every integer
from `score_min` through `score_scale` must be covered exactly once. Set
`score_min` to `0` for zero-based scoring. Sparse exact anchors remain valid;
decimal scores and boundaries are not supported.

## Tips

1. **Anchor extremes first** — define what a 1 and a 5 look like before middle levels.
2. **Use observable behavior** — "cites policy section 4.2" beats "feels helpful."
3. **One dimension per criterion** — split "accurate and concise" into two criteria.
4. **Match your score_scale** — on a 1–5 scale, anchor at least 1, 3, and 5.
5. **Lower juror temperature** — `0.0–0.2` reduces score variance when rubrics are clear.

## Measuring improvement

Compare `juror_agreement` before and after adding rubrics:

```python
print(result.scored_metrics.juror_agreement)  # target: > 0.8
for name, crit in result.criteria_evaluations.items():
    print(f"{name}: agreement={crit.juror_agreement:.2f}")
```

## Related

- [docs/config-schema.md](../docs/config-schema.md)
- [examples/basic_usage/config.json](../examples/basic_usage/config.json)
