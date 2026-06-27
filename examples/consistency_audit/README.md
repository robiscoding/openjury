# Consistency Audit

Measure how reliably your agent produces similar-quality responses to the same prompt.

## What you'll learn

- Setting `num_trials > 1` for consistency audits
- Reading `ConsistencyResult.score_std` and trial scores
- Interpreting variance before deployment

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `OPENROUTER_API_KEY` or `OPENAI_API_KEY` | Per your config |
| `AGENT_API_KEY` | Agent endpoint auth |
| Agent or mock | `python ../tools/mock_agent.py --port 8080` |

## What is a consistency audit?

A standard evaluation (`num_trials=1`) answers: *"How good is this response?"*

A consistency audit (`num_trials > 1`) answers: *"How predictably good is this agent?"*

OpenJury calls the agent endpoint N times for the same prompt, evaluates each response independently with the full jury, and then reports how much the quality scores vary across trials. The primary signal is `score_std` — the standard deviation of the composite scores across trials.

**Why this matters:** High-temperature models or unstable prompts can produce wide swings in response quality. You might observe a 4.5/5 on one run and a 2.8/5 on another. This kind of variance is invisible to single-trial evaluations but important to detect before deployment.

## Trials vs. averaging

Trials are **not** averaged into a single quality score. The composite quality score always comes from trial 1. Trials 2–N exist only to populate `consistency_result`. This matches real-world use: your users each experience one response, not an average.

## Output structure

```
result.composite_score            ← quality (trial 1 weighted_mean)
result.consistency_result         ← populated when num_trials > 1
  .score_std                      ← headline: how much scores varied
  .score_mean                     ← informational; not the quality score
  .score_min / .score_max         ← range across trials
  .trial_composite_scores         ← list of per-trial composites
  .interpretation                 ← human-readable verdict
result.trial_results              ← full per-trial breakdown
  [i].trial_number
  [i].response_text
  [i].scored_metrics
  [i].criteria_evaluations
```

## Interpreting score_std

| `score_std` | Meaning |
|-------------|---------|
| < 0.1 | Low variance — agent is very consistent |
| 0.1–0.3 | Moderate variance — consider reviewing temperature settings |
| ≥ 0.3 | High variance — agent is unpredictable; investigate before shipping |

These thresholds are on the `score_scale` axis (e.g. 1–5).

## Config

Set `num_trials` in your jury config. Max is 5.

```json
{
  "score_scale": 5,
  "num_trials": 3
}
```

Note: `num_trials` multiplies your LLM API calls linearly. For batch datasets, use sparingly or only on representative prompts.

## Files

| File | Purpose |
|------|---------|
| `config.json` | Jury config with `num_trials: 3` |
| `consistency_run.py` | Runs the audit, reads `consistency_result`, prints a deployment decision |

## Running

```bash
export OPENROUTER_API_KEY="..."
export AGENT_API_KEY="..."
python consistency_run.py
```

## CLI

```bash
openjury run \
  --config config.json \
  --endpoints-config ../basic_usage/endpoints.json \
  --prompt "My order hasn't arrived. What should I do?" \
  --consistency-trials 2   # total trials = 1 + 2 = 3 (overrides config num_trials)
```

When `--consistency-trials N` is greater than zero, the CLI sets `num_trials` to `1 + N`, replacing whatever is in `config.json`. Set `num_trials: 1` in the config and use `--consistency-trials` to opt into consistency mode at the CLI level.

## Next steps

- [recipes/consistency-audit-before-ship.md](../../recipes/consistency-audit-before-ship.md)
