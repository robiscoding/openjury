# AGENTS.md — OpenJury

Practical guide for AI coding agents working in this repository. **Repo-specific only** — patterns observed in code, tests, and tooling.

---

## Project Overview

- **What it is:** Python 3.11+ library (`openjury`) for comparing multiple LLM-generated responses using several “juror” models, configurable criteria (Pydantic), and pluggable voting aggregation.
- **Distribution:** Packaged with **Hatchling** (`pyproject.toml`), installable layout under `src/openjury/`.
- **Not in scope:** No application database, no React/TypeScript frontend, no Docker/devcontainer in-repo. “Web” content is an optional **Flask example** under `examples/web_server/`.
- **LLM access:** Jurors use **LangChain** `ChatOpenAI` with API key + base URL from environment (`openjury/env.py`) — works with OpenAI or OpenRouter-style endpoints.

---

## Tech Stack

| Area | Choice |
|------|--------|
| Language | Python ≥ 3.11 |
| Package / build | `pyproject.toml`, Hatchling wheel/sdist, `src/` layout |
| Lock / installer | `uv` + `uv.lock`; Makefile uses `uv run` |
| Config & models | Pydantic v2 (`BaseModel`, `Field`, `model_validate`, enums as `str, Enum`) |
| LLM | `langchain`, `langchain-openai`, `openai` |
| CLI | Typer + Rich |
| Tests | pytest (`tests/`), optional pytest-cov |
| Format / imports | Black (88 cols), isort (black profile) |
| Types | mypy in `[project.optional-dependencies] dev` — **not** run by `make lint` |

---

## Architecture

- **Configuration layer:** `JuryConfig`, `JurorConfig`, `CriterionConfig`, `AgentResponse`, `VotingMethod`, `VotingCriteria` in `src/openjury/config.py`. Loaded via `JuryConfig.from_json_file` / `from_dict` / `from_json`; custom voting hooks register callables on `VotingAggregator`.
- **Endpoint fetching (new):** `endpoint_fetcher.py` — `AgentEndpoint` model, `fetch_all_responses` (parallel via `ThreadPoolExecutor`), SSE streaming support, `${VAR}` env interpolation in headers. Called before `evaluate()` to turn endpoint URLs into `AgentResponse` objects.
- **Execution:** `OpenJury` (`jury_engine.py`) constructs `Juror` instances, runs `evaluate()` per juror (optional `ThreadPoolExecutor` when `parallel_execution` and multiple jurors), collects `JurorEvaluation`, then `VotingAggregator.aggregate()`.
- **LLM boundary:** `Juror` builds prompts via `PromptTemplate` (`prompt_templates.py`), invokes `ChatOpenAI`, parses JSON (with regex fallback) into per-response, per-criterion scores + explanations (`juror.py`).
- **Output:** `VerdictFormatter.create_verdict` builds nested Pydantic `Verdict` / `FinalVerdict` / `JurorVerdict` (`output_format.py`).
- **CLI:** `src/openjury/cli.py` — Typer app `cli_app`; tests invoke `python -m openjury.cli`.

**API/data flow (library):**  
`JuryConfig` → `OpenJury` → concurrent/sync `Juror.evaluate` → `JurorEvaluation[]` → `VotingAggregator` → `VerdictFormatter` → `Verdict`.

---

## Directory Structure

```
.
├── src/openjury/          # Package source (public API mostly re-exported in __init__.py)
├── tests/                 # pytest; conftest.py patches sys.path + env fixtures
├── examples/              # Runnable demos (basic_usage, web_server, custom_voting_method)
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
- **Docs:** `Makefile` target `docs` is a stub (“not yet implemented”).

---

## Coding Standards

- **Style:** Black line length **88**, target py311; isort profile **black**. Lint scope: `src/`, `tests/`, `examples/` (`Makefile`).
- **Typing:** `disallow_untyped_defs = true` in `pyproject.toml` tool.mypy — new code should remain type-annotated where the rest of the module is.
- **Models:** Prefer Pydantic `BaseModel` + `Field(...)` with descriptions (matches existing config/output models).
- **Logging:** Module-level `logger = logging.getLogger(__name__)` pattern (`logger.py` defines optional `setup_logger`; core modules use standard logging).
- **Errors:** Domain exceptions include `OpenJuryInitializationError`, `OpenJuryEvaluationError` (`jury_engine.py`), `JurorException` (`juror.py`), `EnvironmentError` (`env.py`), `EndpointFetchError` (`endpoint_fetcher.py` — HTTP/network failures during response fetching). Voting paths raise `ValueError` with explicit messages (see `tests/test_error_handling.py`).
- **Exports:** Add public symbols to `src/openjury/__init__.py` and `__all__` when exposing new API surface.

---

## API Patterns

- **Construct configs:** `JuryConfig.from_json_file(path, custom_voting_class=None)` — when `voting_method` is `custom`, pass a class with **static methods** to auto-register with `VotingAggregator` (`config.py::_register_custom_methods`).
- **Custom voting:** Functions registered via `VotingAggregator.register_custom_function` must accept `List[JurorEvaluation]` and return `VotingResult` (`voting.py`; examples in `tests/test_custom_voting.py`, `examples/custom_voting_method/`).
- **Evaluation:** `OpenJury.evaluate(prompt, responses, response_ids=None)` — `responses` are `AgentResponse` objects (produced by `fetch_all_responses`); IDs must align if `response_ids` is provided (`jury_engine.py`). Users should not construct `AgentResponse` directly; use endpoint fetching instead.
- **Verdict consumption:** Read `verdict.final_verdict`, `verdict.juror_verdicts`, `verdict.summary`, `verdict.responses` — see `output_format.py` and `tests/test_verdict.py`.

**Example (tests):** Building a verdict without live LLM calls uses `JurorEvaluation` + `VotingAggregator.majority_vote` + `VerdictFormatter.create_verdict` (`tests/test_verdict.py`).

---

## Database Patterns

- **None.** No ORM, migrations, or schema files. Stateful examples may load JSON config from disk only.

---

## Testing

- **Layout:** `tests/test_*.py`, shared fixtures in `tests/conftest.py`.
- **Path hack:** `conftest.py` inserts `repo_root/src` into `sys.path` so tests resolve `openjury` pre-install — prefer running tests via `make test` after editable install for realism.
- **Env:** Autouse fixture sets `OPENROUTER_API_KEY=test-api-key` and `LLM_PROVIDER=openrouter`.
- **CLI tests:** Subprocess `python -m openjury.cli ...` (`tests/test_cli.py`) — does **not** cover `openjury run` happy path.
- **Philosophy:** Heavy unit coverage for voting, verdict formatting, config/custom voting; mocking used where LLM would be called (`mock_juror_evaluations` fixtures, etc.). Integration tests against real APIs are not standard in CI.

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
| `LLM_PROVIDER` | `openrouter` (default) or `openai` (`env.py`) |
| `OPENROUTER_API_KEY` | Required when provider is openrouter |
| `OPENAI_API_KEY` | Required when provider is openai |
| `TWINE_USERNAME` / `TWINE_PASSWORD` | Publishing (CI uses `__token__` + secret) |
| Any user-defined var | Used in `endpoints.json` via `${VAR_NAME}` placeholder in `headers` values. Resolved at fetch time by `endpoint_fetcher.resolve_headers`. Never embed literal API keys in endpoint config files. |

---

## Endpoint Fetching Constraints and Decisions

- **Partial failure is fail-fast:** if any endpoint in `fetch_all_responses` fails, the entire call raises `EndpointFetchError`. Unlike juror failures (which skip-and-proceed), a missing endpoint changes *what is being compared*, so silent dropping is never done. The `batch-eval` per-case `try/except` records this as a case-level error and continues.
- **Endpoint source precedence (batch):** case-level `endpoints` > global `--endpoints-config`. If neither is present for a case, `resolve_endpoint` raises `EndpointFetchError`.
- **Streaming format:** SSE (Server-Sent Events) only in v1. When `stream=True` and `response_path` is at its default (`choices.0.message.content`), the fetcher automatically switches to `choices.0.delta.content` (the per-chunk OpenAI SSE path). Users can override `response_path` for non-OpenAI streaming shapes.
- **No retries:** endpoint fetching has no retry loop (unlike `jury_engine.py`'s `max_retries` for LLM calls). Document this to users; transient failures require a rerun.
- **No new dependencies:** `httpx` was already in `uv.lock` via the `openai` SDK.
- **`EndpointSpec` vs `AgentEndpoint`:** both have identical fields. `EndpointSpec` (in `batch_dataset.py`) exists so JSONL/CSV parsing does not import `httpx` at parse time. `resolve_endpoint` converts `EndpointSpec → AgentEndpoint` just before fetching.

## Important Constraints

- **Python:** `requires-python >= 3.11` — do not rely on 3.10-only syntax.
- **Criteria names in JSON:** Must map to `VotingCriteria` enum values (e.g. `"factuality"`), or validation fails.
- **Juror JSON shape:** Model responses must include scores for **every** response ID and **every** criterion name after parsing; otherwise `Juror.evaluate` retries then raises `JurorException`.
- **Parallel mode:** Failed jurors are **skipped** (logged); evaluation proceeds if at least one succeeds — different from serial path where `JurorException` propagates from `_evaluate_with_juror` (see `jury_engine.py`).
- **Console script:** `pyproject.toml` declares `openjury = "openjury.cli:app"` but `cli.py` defines **`cli_app`**, not `app` — installing the console script may fail until aligned.
- **`VerdictFormatter.criteria_configs` keys** are `VotingCriteria` enums while score dicts use **strings** — lookups fall back to default `max_score` unless aligned (subtle display/metadata bug risk).

---

## Do Not Rules

- Do **not** commit secrets (`.env`, API keys); `.gitignore` includes `.env/` but not `.env` file explicitly — still avoid committing credentials.
- Do **not** assume `ranked` vs `average` vs `consensus` behave differently in code — current `VotingAggregator.ranked_vote`, `average_vote`, and `consensus_vote` share the same high-level pattern (mean of total scores per response); changing one without documenting semantics can mislead users reading README.
- Do **not** edit `uv.lock` by hand unless you intend a lockfile refresh via uv.
- Do **not** treat `examples/custom_voting_method/custom_voting.py` as API truth without verifying field names — some `AgentResponse(...)` calls use kwargs that are **not** model fields (e.g. `model=` vs `model_name`); Pydantic may ignore extras depending on config — prefer matching `AgentResponse` in `config.py`.

---

## Preferred Patterns

- Add voting logic as **`@staticmethod`** methods on a class + registration via `JuryConfig.from_json_file(..., CustomClass)` — matches `examples/custom_voting_method/`.
- Extend evaluation output by enriching **`Verdict`** / **`VerdictFormatter`** rather than ad-hoc dicts on `Verdict`.
- Use **`logger.info` / `logger.warning` / `logger.error`** consistent with `jury_engine.py` and `juror.py`.
- For new criteria, extend **`VotingCriteria`** enum + document JSON serialization name (`factuality`, etc.).
- Tests: mirror **`tests/test_error_handling.py`** for voting edge cases; **`tests/conftest.py`** fixtures for configs/responses.

---

## Anti-Patterns, Deprecated, Legacy, Dangerous, Generated

| Item | Notes |
|------|-------|
| **CLI `run` / table / text paths** | References `verdict.scores`, `verdict.explanations`, `verdict.voting_breakdown`, and `VerdictFormatter().format_verdict(...)` — **`Verdict` has no such attributes/method** in `output_format.py`. Treat CLI beyond `list-jurors` / `export-results` as **broken / out of sync** until fixed. |
| **Entry point `openjury.cli:app`** | Likely broken vs actual `cli_app` symbol — **dangerous for releases**. |
| **`list-jurors` bug** | Uses `config.name` where `config` is a `Path` — should use path string for titles (`cli.py`). |
| **`JuryConfig.from_json_file`** | Uses bare `print()` + broad `except` before re-raise — noisy for library consumers. |
| **`_register_custom_methods`** | Uses `print()` for registration — side-effectful import/config path. |
| **`ranked` / `consensus` naming** | Implementation does not implement rank aggregation as commonly understood — legacy/naming debt relative to README claims. |
| **`uv.lock`** | Generated — regenerate with uv, don’t manually merge casually. |
| **`CONTRIBUTING.md` / `bootstrap.sh`** | Mention `make publish`; Makefile exposes **`release`** / **`release-test`** — docs drift. |

---

## Agent Guidelines

- Read **`src/openjury/config.py`** before changing JSON schema or enums.
- When touching parsing, coordinate **`prompt_templates.py`** (expected JSON shape) with **`juror.py`** `_parse_evaluation_response` and tests.
- Voting changes require updates to **`voting.py`** and **`tests/test_voting.py`** / **`test_error_handling.py`** / **`test_custom_voting.py`** as appropriate.
- After behavioral changes, run **`make check`** (matches CI gates); run **mypy** locally if typing surface changes.
- Examples under **`examples/`** are not CI-gated the same way — still run **`make lint`** if you edit them (included in lint targets).

---

## Safe Change Checklist for AI Agents

**Before editing**

- [ ] Identify whether change affects **config schema**, **prompt/parse**, **voting**, **verdict shape**, or **CLI** — cross-check consumers in `tests/` and `examples/`.
- [ ] Confirm parallel vs serial behavior in `OpenJury.evaluate` if try/except or juror errors change.
- [ ] If adding env vars, update **`env.py`**, **README**, and **tests/conftest.py** as needed.

**Tests to run**

- [ ] `make lint`
- [ ] `make test`
- [ ] If CLI touched: extend **`tests/test_cli.py`** — existing tests only cover `--help`, `list-jurors`, `export-results`.

**Files / consistency**

- [ ] `src/openjury/__init__.py` exports match intended public API.
- [ ] `pyproject.toml` version / `[project.scripts]` align with **`cli.py`** entry symbol.
- [ ] Example JSON configs under **`examples/**/config.json`** remain valid for `JuryConfig.from_json_file`.

**Common regression risks**

- [ ] **Criterion key mismatch** between LLM JSON and `VotingCriteria` string values.
- [ ] **Custom voting** registration collisions on `VotingAggregator._custom_functions` class state across tests (unregister when adding tests).
- [ ] **Silent juror failures** in parallel mode masking systemic prompt/API breakage.
- [ ] **LangChain / OpenAI** argument renames (`model_name` vs `model`) when upgrading dependencies.

---

## Suggested Additional `.cursor/rules/*.mdc` Files

- **`openjury-python.mdc`** — Python 3.11+, Pydantic v2 patterns used here (`Field`, enums), Black/isort, src-layout imports.
- **`openjury-domain.mdc`** — Domain vocabulary: juror, criterion, `AgentResponse`, `VotingMethod`, `JurorEvaluation`, `Verdict`, OpenRouter vs OpenAI env wiring.
- **`openjury-cli-caveats.mdc`** — Document known CLI/entry-point drift so agents don’t “fix” tests without fixing `cli_app`/`app` and `Verdict` accessors together.

---

## Missing Architecture Docs (Would Help Agents)

- **`ARCHITECTURE.md`** — Single diagram + narrative of evaluate → aggregate → verdict; parallel vs serial error semantics.
- **`CLI.md`** — Intended CLI contract once `run`/formats align with `Verdict`.
- **`CONFIG_SCHEMA.md`** — Authoritative JSON schema or generated schema from Pydantic models.
- **Contributing cleanup** — Align Makefile target names with CONTRIBUTING/bootstrap (`release` vs `publish`).
