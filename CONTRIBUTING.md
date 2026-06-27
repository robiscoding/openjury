# Contributing to OpenJury

## SDK user or contributor?

| I want to… | Start here |
|------------|------------|
| **Use OpenJury in my project** | [README.md](README.md) → [examples/hello_world/](examples/hello_world/) → [docs/](docs/README.md) |
| **Contribute code or docs** | This file + [AGENTS.md](AGENTS.md) |

---

## Development setup

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) — fast Python package installer
- [make](https://www.gnu.org/software/make/) — build automation

### Quick start

```bash
git clone https://github.com/robiscoding/openjury.git
cd openjury

# Option 1: bootstrap script
./scripts/bootstrap.sh

# Option 2: make directly
make install-dev
```

### Daily workflow

```bash
make format    # Black + isort
make lint      # format check
make test      # pytest
make check     # lint + test (CI gate)
make pre-commit  # format + lint + test
```

Before opening a PR, run `make check`.

### Architecture and conventions

- [docs/architecture.md](docs/architecture.md) — evaluation flow, concurrency, errors
- [docs/config-schema.md](docs/config-schema.md) — jury JSON reference
- [AGENTS.md](AGENTS.md) — repo-specific guide for AI coding agents

Regenerate JSON Schema after config model changes:

```bash
python scripts/export_config_schema.py
```

---

## Contributing workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Make your changes
4. Run `make check`
5. Commit and push
6. Open a Pull Request

---

## Publishing to PyPI

Maintainers only. Requires PyPI credentials.

### Prerequisites

1. Create a [PyPI account](https://pypi.org/account/register/)
2. Create an [API token](https://pypi.org/manage/account/token/)
3. Configure credentials:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=your-api-token
```

### Release

```bash
make release       # publish to PyPI
make release-test  # publish to TestPyPI
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`):

- **CI:** lint + test on Python 3.11 and 3.12
- **Build:** distribution artifacts on push to `main`
- **Publish:** PyPI release using `TWINE_PASSWORD` secret
