# OpenJury Recipes

Task-oriented how-tos. Each recipe is copy-paste ready.

## By persona

### Eval engineer

- [Score without fetching](score-without-fetching.md) — offline and unit-test workflows
- [Batch eval pipeline](batch-eval-pipeline.md) — JSONL datasets to results
- [Consistency audit before ship](consistency-audit-before-ship.md) — `num_trials` and `score_std`
- [Design rubrics](design-rubrics.md) — improve `juror_agreement`

### Platform engineer

- [Crash recovery resume](crash-recovery-resume.md) — fetch/score split
- [Streaming agent endpoint](streaming-agent-endpoint.md) — SSE configuration
- [CI quality gate](ci-quality-gate.md) — fail build on score threshold

### Research / cost-conscious

- [OpenRouter on a budget](openrouter-on-a-budget.md) — cheap diverse jury
- [Local Ollama jury](local-ollama-jury.md) — zero cloud cost dev loop
- [Mixed provider jury](mixed-provider-jury.md) — OpenAI + Anthropic

### Domain-specific

- [Custom scoring gate](custom-scoring-gate.md) — safety-gated composite scores

## Getting started

New to OpenJury? Start with [hello_world](../examples/hello_world/) then pick a recipe above.

Reference docs: [docs/README.md](../docs/README.md)
