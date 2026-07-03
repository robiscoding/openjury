# Assertions

Run deterministic checks against an agent response without making another LLM
call. Assertions are normally configured per evaluation case and reported
separately from juror-derived scores.

```bash
python assertions_demo.py
```

No API key is required: the script loads `config.json` and evaluates a fixed
response locally.

## Supported types

| Type | Value | Behavior |
|------|-------|----------|
| `contains` | string | Response contains the string |
| `not_contains` | string | Response does not contain the string |
| `equals` | string | Entire response equals the string |
| `not_equals` | string | Entire response differs from the string |
| `starts_with` | string | Response starts with the string |
| `ends_with` | string | Response ends with the string |
| `contains_any` | string list | At least one string occurs |
| `contains_all` | string list | Every string occurs |
| `regex` | string | Python regular expression occurs in the response |
| `min_length` | integer | Character count is at least this value |
| `max_length` | integer | Character count is at most this value |

String and regex assertions accept `"case_sensitive": false`. It defaults to
`true`.

Assertions live in a top-level registry. Each named policy groups one or more
checks with their thresholds:

```json
"assertions": {
  "booking_contract": {
    "checks": [
      {
        "name": "contains confirmation number",
        "type": "regex",
        "value": "CONF-[0-9]+",
        "required": true,
        "weight": 2.0
      }
    ],
    "assertion_threshold": 0.8,
    "quality_threshold": 4.0
  }
}
```

Dataset rows reference a policy by ID:

```json
"dataset": [
  {
    "id": "booking-001",
    "input": "Book the morning flight to Boston.",
    "ground_truth": "The booking should include a confirmation number.",
    "assertion_ids": ["booking_contract"]
  }
]
```

`required` defaults to `true`; `weight` defaults to `1.0`. Policy IDs and
dataset item IDs are free-form strings, but dataset IDs must be unique and each
entry in `assertion_ids` must match a registry key. Checks from multiple
policies are combined; the highest (strictest) threshold wins.

## Reading results

Normal `OpenJury.evaluate()` and `score_existing_response()` results expose:

```python
for assertion in result.assertion_results:
    print(assertion.name, assertion.passed, assertion.detail)

print(result.assertion_score)     # weighted pass rate, 0–1
print(result.assertions_passed)   # every required assertion passed
print(result.passed)              # required + assertion + quality thresholds
```

Each `TrialResult` also has its own `assertion_results`, which matters when
`num_trials` is greater than one. Assertion outcomes do not change the
juror-derived `composite_score`.
