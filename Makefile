.PHONY: help install install-dev clean lint format check test test-cov build dist publish clean-dist clean-cache

help:
	@echo "OpenJury Development Commands:"
	@echo ""
	@echo "Installation:"
	@echo "  install      - Install package in development mode"
	@echo "  install-dev  - Install package with development dependencies"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint         - Run Black, isort, and mypy checks"
	@echo "  format       - Format code with Black and isort"
	@echo "  check        - Run all code quality checks (lint + test)"
	@echo ""
	@echo "Testing:"
	@echo "  test         - Run tests with pytest"
	@echo "  test-cov     - Run tests with coverage report"
	@echo ""
	@echo "Build & Publish:"
	@echo "  build        - Build source distribution and wheel"
	@echo "  dist         - Clean build and create distribution"
	@echo "  publish      - Publish to PyPI using twine"
	@echo ""
	@echo "Cleaning:"
	@echo "  clean        - Remove build artifacts and cache"
	@echo "  clean-dist   - Remove distribution files"
	@echo "  clean-cache  - Remove Python cache files"

install:
	@echo "Installing package in development mode..."
	uv pip install -e .

install-dev:
	@echo "Installing package with development dependencies..."
	uv pip install -e ".[dev]"

lint:
	@echo "Running code quality checks..."
	@echo "Checking code formatting with Black..."
	uv run black --check src/ tests/ examples/
	@echo "Checking import sorting with isort..."
	uv run isort --check-only src/ tests/ examples/
	@echo "Running type checking with mypy..."
	uv run mypy src/

format:
	@echo "Formatting code with Black..."
	uv run black src/ tests/ examples/
	@echo "Sorting imports with isort..."
	uv run isort src/ tests/ examples/

check: lint test

test:
	@echo "Running tests with pytest..."
	uv run pytest tests/ -v

test-cov:
	@echo "Running tests with coverage report..."
	uv run pytest tests/ --cov=openjury --cov-report=term-missing --cov-report=html -v

build:
	@echo "Building source distribution and wheel..."
	uv build

dist: clean-dist build
	@echo "Distribution files created in dist/"

publish: dist
	@echo "Publishing to PyPI..."
	@echo "Make sure you have configured your PyPI credentials!"
	twine upload dist/*

publish-test: dist
	@echo "Publishing to TestPyPI..."
	@echo "Make sure you have configured your TestPyPI credentials!"
	twine upload --repository testpypi dist/*

clean: clean-dist clean-cache
	@echo "Cleaned build artifacts and cache"

clean-dist:
	@echo "Removing distribution files..."
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/

clean-cache:
	@echo "Removing Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .coverage
	rm -rf htmlcov/

dev-setup: install-dev
	@echo "Development environment setup complete!"

pre-commit: format lint test
	@echo "Pre-commit checks passed!"

docs:
	@echo "Building documentation..."
	@echo "Documentation build not yet implemented"

release: clean check dist publish
	@echo "Release completed successfully!"

release-test: clean check dist publish-test
	@echo "Release to TestPyPI completed successfully!"

dev: format test
	@echo "Development cycle completed!" 