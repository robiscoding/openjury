# CLI Reference

Install the console script with `pip install openjury`, then run `openjury --help`.

Alternative: `python -m openjury.cli`

## Commands

| Command | Description |
|---------|-------------|
| `run` | Evaluate prompt(s) against agent endpoint(s) |
| `batch-eval` | Run an inline config, JSONL, or CSV dataset through a jury |
| `list-jurors` | Show jurors from a config or built-in criterion names |
| `list-configs` | List example JSON configs or print sample structure |
| `export-results` | Convert results JSONL to CSV/JSON summary |

## run

Evaluate one or more prompts:

```bash
export OPENAI_API_KEY="..." AGENT_API_KEY="..."

openjury run \
  --config jury_config.json \
  --endpoints-config endpoints.json \
  --prompt "How do I reset my password?"
```

### Options

| Flag | Description |
|------|-------------|
| `--config`, `-c` | Jury config JSON (required) |
| `--endpoints-config`, `-e` | Endpoints JSON (required) |
| `--prompt`, `-p` | Single prompt |
| `--prompts-file`, `-P` | `.txt` (one per line) or `.jsonl` prompts file |
| `--consistency-trials N` | Sets `num_trials = 1 + N` (replaces config value) |
| `--references` | Calibration examples for jurors |
| `--case-rules` | Per-evaluation rules text |
| `--output`, `-o` | Write results to file |
| `--format`, `-f` | `text` (default) or `json` |
| `--verbose`, `-v` | Verbose logging |

### Consistency trials

```bash
openjury run \
  --config config.json \
  --endpoints-config endpoints.json \
  --prompt "Test prompt" \
  --consistency-trials 2
```

Total trials = 3 (trial 1 = quality; trials 2–3 measure consistency).

## batch-eval

```bash
openjury batch-eval \
  --config jury_config.json \
  --endpoints-config endpoints.json \
  --output results.jsonl
```

When the config contains `dataset`, `--input` is optional. Supplying it
overrides the inline dataset:

```bash
openjury batch-eval \
  --config jury_config.json \
  --input dataset.jsonl \
  --output results.jsonl
```

Global endpoint fallback:

```bash
openjury batch-eval \
  --config jury_config.json \
  --input dataset.jsonl \
  --endpoints-config endpoints.json \
  --output results.jsonl
```

### batch-eval options

| Flag | Description |
|------|-------------|
| `--config`, `-c` | Jury config JSON (required) |
| `--input`, `-i` | JSONL/CSV dataset; omit to use inline `config.dataset` |
| `--output`, `-o` | Output JSONL path (required) |
| `--endpoints-config`, `-e` | Global endpoint fallback for cases without inline endpoints |
| `--limit`, `-n` | Maximum number of cases to run |
| `--workers`, `-w` | Concurrent item evaluations (default: 1) |
| `--summary-output` | Optional path for run-level `BatchRunSummary` JSON |
| `--verbose`, `-v` | Verbose logging |

Each JSONL row includes legacy fields (`case_id`, `error`, `eval`) plus
`status`, `error_code`, `error_stage`, and `evaluation_duration_ms`. Successful
rows embed enriched per-item fields inside `eval` (`item_id`, `quality_passed`,
`contested`, `lowest_criterion`, and more).

## list-jurors

```bash
openjury list-jurors --config examples/basic_usage/config.json
openjury list-jurors  # lists built-in VotingCriteria names
```

## list-configs

```bash
openjury list-configs --examples-dir examples/
openjury list-configs  # prints valid sample config structure
```

## export-results

```bash
openjury export-results \
  --input results.jsonl \
  --output summary.csv \
  --format csv
```

Optionally derive a batch summary from existing JSONL rows:

```bash
openjury export-results \
  --input results.jsonl \
  --output summary.csv \
  --format csv \
  --summary-output summary.json
```

## Local development with mock agent

```bash
# Terminal 1
python examples/tools/mock_agent.py --port 8080

# Terminal 2
export AGENT_API_KEY=demo OPENAI_API_KEY=sk-...
openjury run \
  --config examples/basic_usage/config.json \
  --endpoints-config examples/basic_usage/endpoints.json \
  --prompt "How do I reset my password?"
```

## Note on test coverage

`list-jurors` and `export-results` have CLI tests. `run` and `batch-eval` happy paths are not yet covered in CI — report regressions via GitHub issues.
