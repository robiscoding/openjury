# AGENTS.md — OpenJury

Practical guide for AI coding agents working in this repository. **Repo-specific only** — patterns observed in code, tests, and tooling.

---

## Project Overview

- **What it is:** Python 3.11+ library (`openjury`) for evaluating a single LLM agent's responses against configurable criteria (Pydantic), using multiple "juror" models that produce scores aggregated into rich metrics.
- **Distribution:** Packaged with **Hatchling** (`pyproject.toml`), installable layout under `src/openjury/`.
- **Not in scope:** No application database, no React/TypeScript frontend, no Docker/devcontainer in-repo. "Web" content is an optional **Flask example** under `examples/web_server/`.
- **LLM access:** Jurors use `ChatOpenAI` (openai_compatible) or `ChatAnthropic` (anthropic), configured via `LLMProviderConfig` in the JSON config — **not** environment variables. `${VAR}` placeholders in `api_key`/`base_url` are expanded at init time via `expand_env_vars` (`env.py`).

---

## Tech Stack

| Area | Choice |
|------|--------|
| Language | Python ≥ 3.11 |
| Package / build | `pyproject.toml`, Hatchling wheel/sdist, `src/` layout |
| Lock / installer | `uv` + `uv.lock`; Makefile uses `uv run` |
| Config & models | Pydantic v2 (`BaseModel`, `Field`, `model_validate`, enums as `str, Enum`) |
| LLM | `langchain-openai`; optional `langchain-anthropic` (`openjury[anthropic]`) |
| CLI | Typer + Rich |
| Tests | pytest (`tests/`), optional pytest-cov |
| Format / imports | Black (88 cols), isort (black profile) |
| Types | mypy in `[project.optional-dependencies] dev` — **not** run by `make lint` |

---

## Architecture

- **Configuration layer:** `JuryConfig`, `JurorConfig`, `LLMProviderConfig`, `CriterionConfig`, `AssertionConfig`, `AgentResponse`, `JurorProvider`, `AssertionType`, `VotingCriteria` in `src/openjury/config.py`. Loaded via `JuryConfig.from_json_file` / `from_dict` / `from_json`. LLM credentials travel with the config, not from env vars.
- **Provider resolution:** `resolve_juror_llm_config(juror, jury_llm_provider)` in `config.py` — jurors either inherit the jury-level `llm_provider` or fully override it by setting `model_name + api_key + provider` together on `JurorConfig`. Partial overrides are rejected at validation time.
- **Endpoint fetching:** `endpoint_fetcher.py` — `fetch_agent_response()`, `AgentEndpoint`, SSE streaming with limits/metadata, `${VAR}` env interpolation, `{prompt}`/`{ground_truth}` template substitution. Called inside `evaluate()` before juror scoring.
- **Execution:** `OpenJury` (`jury_engine.py`) constructs `Juror` instances. Public methods: `evaluate()`, `score_existing_response()`, `evaluate_items()`, `run_jurors()`, `score_batch()`. Juror concurrency via `ExecutionOptions.max_juror_workers`; item concurrency via `max_item_workers`. Outbound calls share `ExecutionOptions.outbound_slot()` semaphore.
- **LLM boundary:** `Juror` builds prompts via `PromptTemplate` (`prompt_templates.py`), invokes the appropriate LLM (`ChatOpenAI` or `ChatAnthropic`), parses JSON (with regex fallback) into per-criterion scores + explanations (`juror.py`).
- **Scoring:** `ScoreAggregator.compute_all` (`scoring.py`) produces `ScoredMetrics` — `weighted_mean`, `mean`, `median`, `harmonic_mean`, `weakest_link`, `juror_agreement`, optional `custom`. All values are on the `score_scale` axis.
- **Assertions:** `assertions.py` evaluates deterministic response checks and `score_assertions()` computes their weighted pass rate. Assertions are independent from juror quality scoring: they never alter `composite_score`. `JuryConfig.assertion_threshold` and `quality_threshold` only participate in the final `passed` decision.
- **Consistency audit:** When `num_trials > 1`, `evaluate()` reruns the agent N times and calls `ScoreAggregator.compute_consistency` to produce a `ConsistencyResult` (std, mean, min, max, interpretation). Quality score always comes from trial 1.
- **Output:** `AgentEvalResult` / `CriterionEvaluation` / `TrialResult` in `output_format.py`. `ResultFormatter.format_result(result)` produces human-readable text. `OpenJury.format_result(result)` is a static alias.
- **CLI:** `src/openjury/cli.py` — Typer app `cli_app`; tests invoke `python -m openjury.cli`.

**API/data flow (library):**
`JuryConfig` → `OpenJury` → `evaluate(prompt, endpoint, options)` → `fetch_agent_response` → juror scoring via `ScoreAggregator.compute_all` + deterministic checks via `evaluate_assertions` / `score_assertions` → `AgentEvalResult`.

---

## Directory Structure

```
.
├── src/openjury/          # Package source (public API mostly re-exported in __init__.py)
├── tests/                 # pytest; conftest.py patches sys.path + shared fixtures
├── examples/              # Runnable demos (basic_usage, web_server, custom_voting_method)
│   └── provider_configs/  # Example JSON configs for different LLM provider setups
├── scripts/bootstrap.sh   # Dev bootstrap (uv + make install-dev)
├── Makefile               # lint, format, test, build, release helpers
├── pyproject.toml         # deps, tool configs, console script entry
├── uv.lock                # Dependency lock (uv); treat as generated
├── .github/workflows/ci.yml
├── README.md / CONTRIBUTING.md
└── LICENSE
```

---

## Development Workflow

- **Bootstrap:** `./scripts/bootstrap.sh` or `make install-dev` (expects `uv` and `make`).
- **Day-to-day:** `make format` → `make lint` → `make test`; or `make check` (lint + test); `make dev` formats + tests.
- **Pre-commit-style:** `make pre-commit` runs format, lint, test (CONTRIBUTING also mentions this).
- **CI:** `.github/workflows/ci.yml` — on PR/push to `main`: Python 3.11 & 3.12, `uv pip install -e ".[dev]"`, `make lint`, `make test`. On push to `main` only: build artifact upload + PyPI release job using `TWINE_PASSWORD` secret.
- **Docs:** `Makefile` target `docs` is a stub ("not yet implemented").

---

## Coding Standards

- **Style:** Black line length **88**, target py311; isort profile **black**. Lint scope: `src/`, `tests/`, `examples/` (`Makefile`).
- **Typing:** `disallow_untyped_defs = true` in `pyproject.toml` tool.mypy — new code should remain type-annotated where the rest of the module is.
- **Models:** Prefer Pydantic `BaseModel` + `Field(...)` with descriptions (matches existing config/output models).
- **Logging:** Module-level `logger = logging.getLogger(__name__)` pattern (`logger.py` defines optional `setup_logger`; core modules use standard logging).
- **Errors:** `ConfigurationError` (`env.py`) for missing/invalid LLM config. `OpenJuryInitializationError`, `OpenJuryEvaluationError` (`jury_engine.py`). `JurorException` (`juror.py`). `EndpointFetchError` (`endpoint_fetcher.py`). `ValueError` with explicit messages in scoring paths.
- **Exports:** Add public symbols to `src/openjury/__init__.py` and `__all__` when exposing new API surface.

---

## API Patterns

- **Construct config:** `JuryConfig.from_json_file(path)` — no `custom_voting_class` parameter; custom scoring is registered via `ScoreAggregator.register()` separately.
- **Custom scoring:** Register a `ScoringFunction` (i.e. `Callable[[List[JurorScore], List[CriterionConfig]], float]`) via `ScoreAggregator.register(name, fn)`. Reference by name in `JuryConfig.custom_scoring_function`. Produces `ScoredMetrics.custom`.
- **Per-juror provider override:** Set `model_name`, `api_key`, and `provider` **all together** on `JurorConfig` to override the jury-level `llm_provider`. Setting any subset raises `ValidationError` at config construction time.
- **Evaluation:** `OpenJury.evaluate(prompt, endpoint, options=...)` returns `AgentEvalResult`. `score_existing_response(prompt, agent_response, ...)` scores without fetching. `evaluate_items(items, endpoint, options=...)` runs bounded batch evaluation. `score_batch(prompts, endpoint)` is sequential fail-fast over `evaluate_items`. `score_response()` is an alias for `evaluate()`.
- **Assertions:** Configure `JuryConfig.assertions` with `AssertionConfig(name, type, value, required=True, weight=1.0, case_sensitive=True)`. Supported types are `contains`, `not_contains`, `equals`, `not_equals`, `starts_with`, `ends_with`, `contains_any`, `contains_all`, `regex`, `min_length`, and `max_length`. Assertion weights must be positive.
- **Assertion policy:** `assertion_score` is `sum(weight for passed assertions) / sum(all assertion weights)`. `assertions_passed` means every assertion with `required=True` passed. With no assertions, these values are `1.0` and `True`. Optional `JuryConfig.assertion_threshold` is on the 0–1 axis; optional `quality_threshold` is on the `score_scale` axis and cannot exceed it.
- **Overall status:** `AgentEvalResult.passed` is true only when all required assertions pass, the optional assertion threshold is met, and the optional quality threshold is met. Neither threshold changes `composite_score`.
- **Consistency audit:** Set `num_trials > 1` in `JuryConfig`. `AgentEvalResult.consistency_result` is populated with `ConsistencyResult`; `trial_results` contains all `TrialResult` objects.
- **Result consumption:** Read `result.composite_score`, `result.normalized_composite_score`, `result.assertion_score`, `result.assertions_passed`, `result.passed`, `result.assertion_results`, `result.scored_metrics`, `result.criteria_evaluations`, and `result.consistency_result` — see `output_format.py`. Each `TrialResult` also carries its own assertion results, score, and required-policy status.

**Example (tests):** `test_provider_resolution.py` — unit tests for `resolve_juror_llm_config`, `expand_env_vars`, `Juror` construction, Anthropic dispatch.

---

## Provider Configuration

`LLMProviderConfig` is required on `JuryConfig` (as `llm_provider`) unless every juror fully overrides with its own `model_name + api_key + provider`. Both `api_key` and `base_url` support `${ENV_VAR}` interpolation expanded at `Juror` init time.

`JurorProvider` enum values:
- `"openai_compatible"` — works with OpenAI, OpenRouter, xAI, Gemini, Ollama, vLLM, LiteLLM, or any OpenAI-compatible endpoint. Uses `ChatOpenAI`.
- `"anthropic"` — Anthropic API directly. Requires `pip install openjury[anthropic]`. Uses `ChatAnthropic`. No `base_url`.

See `examples/provider_configs/` for ready-to-use configs for OpenAI, OpenRouter, Ollama, mixed-provider juries, self-hosted gateways, and per-juror overrides.

---

## Database Patterns

- **None.** No ORM, migrations, or schema files. Stateful examples may load JSON config from disk only.

---

## Testing

- **Layout:** `tests/test_*.py`, shared fixtures in `tests/conftest.py`.
- **Path hack:** `conftest.py` inserts `repo_root/src` into `sys.path` so tests resolve `openjury` pre-install — prefer running tests via `make test` after editable install for realism.
- **Fixtures:** `sample_criteria`, `sample_llm_provider` (`LLMProviderConfig`), `sample_jurors`, `sample_jury_config`, `sample_response`, `sample_prompt` — no autouse env var fixture; env vars for LLM auth are no longer needed by the library itself.
- **CLI tests:** Subprocess `python -m openjury.cli ...` (`tests/test_cli.py`) — does **not** cover `openjury run` happy path.
- **Provider tests:** `tests/test_provider_resolution.py` covers `expand_env_vars`, `resolve_juror_llm_config`, `Juror` construction for both providers, and `OpenJury` credential passthrough.
- **Assertion tests:** `tests/test_assertions.py` covers assertion types, validation, weighting, and required policy. `tests/test_jury_engine.py` verifies thresholds and that assertion failures do not change `composite_score`.
- **Philosophy:** Heavy unit coverage for scoring, output formatting, config, provider resolution; mocking used where LLM would be called. Integration tests against real APIs are not standard in CI.

---

## Common Commands

| Command | Purpose |
|---------|---------|
| `make install-dev` | Editable install + dev extras via uv |
| `make format` | Black + isort write |
| `make lint` | Black --check + isort --check-only |
| `make test` | `pytest tests/ -v` |
| `make test-cov` | Pytest with coverage HTML + terminal |
| `make check` | lint + test |
| `make build` / `make dist` | Build wheels/sdist |
| `uv run mypy src/openjury` | Types (manual; not in Makefile) |

---

## Environment Variables

| Variable | Role |
|----------|------|
| `${ANY_VAR}` in config JSON | `api_key` and `base_url` in `LLMProviderConfig` / `JurorConfig` support `${VAR_NAME}` interpolation, expanded by `expand_env_vars` at `Juror` init time. Missing vars raise `ConfigurationError`. |
| Any user-defined var | Also used in `endpoints.json` `headers` values via `${VAR_NAME}`. Resolved at fetch time by `endpoint_fetcher`. Never embed literal API keys in config files. |
| `TWINE_USERNAME` / `TWINE_PASSWORD` | Publishing (CI uses `__token__` + secret) |

`LLM_PROVIDER`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY` are **no longer used by the library** — provider and credentials live in `LLMProviderConfig` inside the jury config JSON.

---

## Endpoint Fetching Constraints and Decisions

- **Partial failure is fail-fast:** if any endpoint in `fetch_all_responses` fails, the entire call raises `EndpointFetchError`. Unlike juror failures (which skip-and-proceed), a missing endpoint changes *what is being compared*.
- **Endpoint source precedence (batch):** case-level `endpoints` > global `--endpoints-config`. If neither is present for a case, `resolve_endpoint` raises `EndpointFetchError`.
- **Streaming format:** SSE (Server-Sent Events) only in v1. When `stream=True` and `response_path` is at its default (`choices.0.message.content`), the fetcher automatically switches to `choices.0.delta.content`. Users can override `response_path` for non-OpenAI streaming shapes.
- **No retries:** endpoint fetching has no retry loop (unlike `jury_engine.py`'s `max_retries` for LLM juror calls). Transient failures require a rerun.
- **No new dependencies:** `httpx` was already in `uv.lock` via the `openai` SDK.
- **`EndpointSpec` vs `AgentEndpoint`:** both have identical fields. `EndpointSpec` (in `batch_dataset.py`) exists so JSONL/CSV parsing does not import `httpx` at parse time. `resolve_endpoint` converts `EndpointSpec → AgentEndpoint` just before fetching.

---

## Important Constraints

- **Python:** `requires-python >= 3.11` — do not rely on 3.10-only syntax.
- **Criteria names are free-form strings:** `VotingCriteria` is a convenience enum only — `CriterionConfig.name` accepts any string. Enum member names/values are auto-coerced but not required. The old constraint "must map to `VotingCriteria` enum values" no longer applies.
- **Juror JSON shape:** Model responses must include scores for **every** criterion name after parsing; otherwise `Juror.evaluate` retries then raises `JurorException`.
- **Score axes stay separate:** `composite_score` is subjective juror quality on the configured `score_scale`; `assertion_score` is a deterministic weighted pass rate on 0–1. Do not blend assertions into `composite_score`.
- **Assertion defaults:** Assertions default to `required=True`, `weight=1.0`, and `case_sensitive=True`. A failed optional assertion lowers `assertion_score` but does not make `assertions_passed` false. A failed required assertion makes `assertions_passed` and overall `passed` false even when the weighted threshold is met.
- **Parallel mode:** Failed jurors are **skipped** (logged); evaluation proceeds if at least one succeeds. Serial path also skips-and-continues (both paths use try/except in `run_jurors`). An all-juror failure raises `OpenJuryEvaluationError` (or returns partial `ScoringResult` when `raise_if_all_jurors_failed=False`).
- **`parallel_execution`** is deprecated on `OpenJury` — prefer `ExecutionOptions(max_juror_workers=1)` for serial jurors. Still accepted with `DeprecationWarning`.
- **Console script:** `pyproject.toml` declares `openjury = "openjury.cli:app"` but `cli.py` defines **`cli_app`**, not `app` — installing the console script may fail until aligned.
- **Anthropic extra:** `langchain-anthropic` is an optional dependency. Using `provider: "anthropic"` without installing it raises `ImportError` with an install hint.

---

## Do Not Rules

- Do **not** commit secrets (`.env`, API keys); use `${VAR_NAME}` placeholders in config JSON instead.
- Do **not** edit `uv.lock` by hand unless you intend a lockfile refresh via uv.
- Do **not** treat `examples/custom_voting_method/custom_voting.py` as API truth — the old `VotingAggregator` / `AgentResponse(model=...)` patterns it may reference are from a prior architecture. Custom scoring now uses `ScoreAggregator.register()`.
- Do **not** reference the old output types (`Verdict`, `FinalVerdict`, `JurorVerdict`, `VerdictFormatter`, `JurorEvaluation`, `VotingResult`, `VotingAggregator`) — they no longer exist. The equivalent types are `AgentEvalResult`, `TrialResult`, `JurorScore`, `ScoredMetrics`, `ScoreAggregator`.

---

## Preferred Patterns

- Register custom scoring functions via **`ScoreAggregator.register(name, fn)`** and reference by name in `JuryConfig.custom_scoring_function`.
- Use **`evaluate_assertions()` + `score_assertions()`** when constructing `AgentEvalResult` manually; otherwise the default `assertion_score=1.0` and `assertions_passed=True` may not match supplied assertion results.
- Extend evaluation output by enriching **`AgentEvalResult`** / **`CriterionEvaluation`** / **`TrialResult`** rather than ad-hoc dicts.
- Use **`logger.info` / `logger.warning` / `logger.error`** consistent with `jury_engine.py` and `juror.py`.
- For new criteria, use any descriptive string name. `VotingCriteria` enum values are a reference but not a constraint.
- Tests: mirror **`tests/test_provider_resolution.py`** for provider/config edge cases; **`tests/conftest.py`** fixtures for jury configs.

---

## Anti-Patterns, Deprecated, Legacy, Dangerous, Generated

| Item | Notes |
|------|-------|
| **CLI `run` / table / text paths** | May reference stale `Verdict` attributes or `VerdictFormatter().format_verdict(...)` — **`Verdict` no longer exists**. Treat CLI beyond `list-jurors` / `export-results` as potentially out of sync until audited against current `AgentEvalResult`. |
| **Entry point `openjury.cli:app`** | Broken vs actual `cli_app` symbol in `cli.py` — **dangerous for releases**. |
| **`list-jurors` bug** | Uses `config.name` where `config` is a `Path` — should use path string for titles (`cli.py`). |
| **Old env var LLM wiring** | `LLM_PROVIDER`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY` are no longer used by the library. Code or docs referencing them for juror configuration is legacy. |
| **`VotingAggregator` / `VotingMethod` / `Verdict`** | Fully removed. Do not attempt to import. Replaced by `ScoreAggregator` / `ScoredMetrics` / `AgentEvalResult`. |
| **`ranked` / `consensus` / `majority` voting** | These `VotingMethod` variants no longer exist. |
| **`JuryConfig.from_json_file(path, custom_voting_class=...)`** | `custom_voting_class` parameter no longer exists. |
| **`uv.lock`** | Generated — regenerate with uv, don't manually merge casually. |
| **`CONTRIBUTING.md` / `bootstrap.sh`** | Mention `make publish`; Makefile exposes **`release`** / **`release-test`** — docs drift. |

---

## Agent Guidelines

- Read **`src/openjury/config.py`** before changing JSON schema or enums — especially `LLMProviderConfig`, `JurorConfig.validate_provider_override`, and `resolve_juror_llm_config`.
- When changing assertions, coordinate **`config.py`**, **`assertions.py`**, **`jury_engine.py`**, **`output_format.py`**, exports in **`__init__.py`**, and **`tests/test_assertions.py`**.
- When touching parsing, coordinate **`prompt_templates.py`** (expected JSON shape) with **`juror.py`** `_parse_evaluation_response` and tests.
- Scoring changes require updates to **`scoring.py`** and its consumers in `jury_engine.py`, `output_format.py`, and relevant tests.
- After behavioral changes, run **`make check`** (matches CI gates); run **mypy** locally if typing surface changes.
- Examples under **`examples/`** are not CI-gated the same way — still run **`make lint`** if you edit them (included in lint targets).

---

## Safe Change Checklist for AI Agents

**Before editing**

- [ ] Identify whether change affects **config schema**, **provider resolution**, **prompt/parse**, **scoring**, **output format**, or **CLI** — cross-check consumers in `tests/` and `examples/`.
- [ ] If assertions change, preserve the separation between juror quality and deterministic assertion scoring; verify required, optional, weighted, threshold, and empty-set behavior.
- [ ] Confirm parallel vs serial behavior in `OpenJury._run_jurors` if try/except or juror errors change (both paths now skip-and-continue).
- [ ] If adding env vars, update **`env.py`** (if adding new `ConfigurationError` cases), **README**, and relevant tests.

**Tests to run**

- [ ] `make lint`
- [ ] `make test`
- [ ] If provider/config touched: check **`tests/test_provider_resolution.py`**.
- [ ] If assertions touched: run **`tests/test_assertions.py`** and relevant engine/serialization tests.
- [ ] If CLI touched: extend **`tests/test_cli.py`** — existing tests only cover `--help`, `list-jurors`, `export-results`.

**Files / consistency**

- [ ] `src/openjury/__init__.py` exports match intended public API.
- [ ] `pyproject.toml` version / `[project.scripts]` align with **`cli.py`** entry symbol.
- [ ] Example JSON configs under **`examples/**/config.json`** remain valid for `JuryConfig.from_json_file`.

**Common regression risks**

- [ ] **Criterion key mismatch** between LLM JSON output and `CriterionConfig.name` values.
- [ ] **Assertion/result mismatch** when manually constructing results without calling `score_assertions()`.
- [ ] **Score-axis confusion** between 0–1 `assertion_threshold` and 1–`score_scale` `quality_threshold`.
- [ ] **Required assertion masking** if overall `passed` checks only the weighted threshold and omits `assertions_passed`.
- [ ] **Custom scoring** registration collisions on `ScoreAggregator._custom_functions` class state across tests — call `ScoreAggregator.unregister(name)` in test teardown.
- [ ] **Silent juror failures** in parallel mode masking systemic prompt/API breakage.
- [ ] **LangChain / OpenAI** argument renames (`model_name` vs `model`) when upgrading dependencies.
- [ ] **`parallel_execution`** in a JSON config is silently ignored by Pydantic (extra fields) — pass it to `OpenJury(config, parallel_execution=...)` constructor instead.

---

## Suggested Additional `.cursor/rules/*.mdc` Files

- **`openjury-python.mdc`** — Python 3.11+, Pydantic v2 patterns used here (`Field`, enums, `model_validator`), Black/isort, src-layout imports.
- **`openjury-domain.mdc`** — Domain vocabulary: juror, criterion, `AgentResponse`, `LLMProviderConfig`, `JurorProvider`, `ScoreAggregator`, `AgentEvalResult`, `ConsistencyResult`, `num_trials`.
- **`openjury-cli-caveats.mdc`** — Document known CLI/entry-point drift so agents don't "fix" tests without fixing `cli_app`/`app` and stale `Verdict` attribute references together.

---

## Missing Architecture Docs (Would Help Agents)

- **`ARCHITECTURE.md`** — Single diagram + narrative of score_response → aggregate → AgentEvalResult; parallel vs serial error semantics; consistency audit flow.
- **`CLI.md`** — Intended CLI contract once `run`/formats align with `AgentEvalResult`.
- **`CONFIG_SCHEMA.md`** — Authoritative JSON schema or generated schema from Pydantic models (especially `LLMProviderConfig` + per-juror overrides, which are easy to misconfigure).
- **Contributing cleanup** — Align Makefile target names with CONTRIBUTING/bootstrap (`release` vs `publish`).
