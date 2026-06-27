# CI Quality Gate

Fail a CI job when agent quality drops below a threshold.

## GitHub Actions example

```yaml
name: Agent Quality Gate

on:
  pull_request:
    paths:
      - "agent/**"
      - "prompts/**"

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"

      - run: uv pip install -e .

      - name: Start mock agent
        run: python examples/tools/mock_agent.py --port 8080 &
        env:
          AGENT_API_KEY: demo

      - name: Run evaluation
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          AGENT_API_KEY: demo
        run: |
          python - <<'EOF'
          from openjury import JuryConfig, OpenJury
          from openjury.endpoint_fetcher import load_endpoints_file

          jury = OpenJury(JuryConfig.from_json_file("examples/basic_usage/config.json"))
          endpoint = load_endpoints_file("examples/basic_usage/endpoints.json")[0]
          result = jury.evaluate("How do I reset my password?", endpoint)

          threshold = 3.5
          score = result.composite_score
          print(f"Score: {score:.2f} (threshold: {threshold})")
          if score < threshold:
              raise SystemExit(f"Quality gate failed: {score:.2f} < {threshold}")
          EOF
```

## Tips

- Pin jury config in repo; review changes in PRs
- Use `score_existing_response()` with fixture responses for deterministic CI without agent calls
- Export `serialize_eval_result()` artifacts for trend tracking

## Related

- [examples/hello_world/](../examples/hello_world/) — offline fixture pattern
- [recipes/score-without-fetching.md](score-without-fetching.md)
