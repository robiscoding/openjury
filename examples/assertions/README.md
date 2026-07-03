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

Assertions are configured in three layers:

1. **`global_assertions`** — applied automatically to every item
2. **`assertion_profiles`** — reusable contracts selected via `assertion_profile_ids`
3. **`dataset[].assertions`** — optional inline supplements per row

```json
"global_assertions": [
  {
    "name": "not empty",
    "type": "min_length",
    "value": 1,
    "required": true
  }
],
"assertion_profiles": {
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

Dataset rows reference profiles by ID and may supply template variables:

```json
"dataset": [
  {
    "id": "booking-001",
    "input": "Book the morning flight to Boston.",
    "ground_truth": "The booking should include a confirmation number.",
    "assertion_profile_ids": ["booking_contract"]
  }
]
```

Use `{{key}}` in profile assertion values when item-specific substitution is needed:

```json
"variables": {"order_number": "12345"},
"assertion_profile_ids": ["order_status_contract"]
```

`required` defaults to `true`; `weight` defaults to `1.0`. Profile IDs and dataset
item IDs are free-form strings, but dataset IDs must be unique and each profile
reference must match a registry key. Threshold precedence: item override →
single selected profile → `assertion_policy` defaults.

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
