# Development Guide

This guide explains how to set up and use the development environment for OpenJury.

### Development Workflow

OpenJury uses a modern, Makefile-powered development workflow:


## Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [make](https://www.gnu.org/software/make/) - Build automation tool

## Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/robiscoding/openjury.git
   cd openjury
   ```

2. **Set up development environment:**
   ```bash
   # Option 1: Use the setup script
   ./scripts/bootstrap.sh
   
   # Option 2: Use make directly
   make install-dev
   ```

3. **Run tests:**
   ```bash
   make test
   ```

## Publishing to PyPI

### Prerequisites

1. **Create PyPI account:**
   - Go to [PyPI](https://pypi.org/account/register/)
   - Create an account and verify your email

2. **Create API token:**
   - Go to [PyPI API tokens](https://pypi.org/manage/account/token/)
   - Create a new token with "Entire account" scope

3. **Configure credentials:**
   ```bash
   # Option 1: Environment variables
   export TWINE_USERNAME=__token__
   export TWINE_PASSWORD=your-api-token
   
   # Option 2: ~/.pypirc file
   cat > ~/.pypirc << EOF
   [distutils]
   index-servers =
       pypi
       testpypi
   
   [pypi]
   repository = https://upload.pypi.org/legacy/
   username = __token__
   password = your-api-token
   
   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = your-test-token
   EOF
   ```

## CI/CD Integration

The project includes GitHub Actions workflows that use the Makefile:

- **CI Pipeline** (`ci` job): Runs linting and tests on multiple Python versions
- **Build Pipeline** (`build` job): Creates distribution files
- **Publish Pipeline** (`publish` job): Publishes to PyPI

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run quality checks: `make pre-commit`
5. Commit your changes: `git commit -m 'Add amazing feature'`
6. Push to the branch: `git push origin feature/amazing-feature`
7. Open a Pull Request
