.PHONY: help install install-dev clean lint format check test test-cov build dist release release-test clean-dist clean-cache

help:
	@echo "OpenJury Development Commands:"
	@echo ""
	@echo "Installation:"
	@echo "  install      - Install package in development mode"
	@echo "  install-dev  - Install package with development dependencies"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint         - Run Black, isort"
	@echo "  format       - Format code with Black and isort"
	@echo "  check        - Run all code quality checks (lint + test)"
	@echo ""
	@echo "Testing:"
	@echo "  test         - Run tests with pytest"
	@echo "  test-cov     - Run tests with coverage report"
	@echo ""
	@echo "Build & Release:"
	@echo "  build        - Build source distribution and wheel"
	@echo "  dist         - Clean build and create distribution"
	@echo "  release      - Release to PyPI (CI/CD use with pre-built artifacts)"
	@echo "  release-test - Build and release to TestPyPI (local development)"
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

release:
	@echo "Releasing to PyPI..."
	@echo "This target is designed for CI/CD with pre-built artifacts"
	@if [ ! -d "dist" ] || [ -z "$$(ls -A dist/ 2>/dev/null)" ]; then \
		echo "Error: No distribution files found in dist/ directory"; \
		echo "Run 'make dist' first or use this target in CI/CD pipeline"; \
		exit 1; \
	fi
	@echo "Checking distribution files..."
	twine check dist/*
	@echo "Uploading to PyPI..."
	twine upload dist/*

release-test: clean check dist
	@echo "Releasing to TestPyPI..."
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
	rm -rf .coverage
	rm -rf htmlcov/

dev-setup: install-dev
	@echo "Development environment setup complete!"

pre-commit: format lint test
	@echo "Pre-commit checks passed!"

docs:
	@echo "Building documentation..."
	@echo "Documentation build not yet implemented"

dev: format test
	@echo "Development cycle completed!" 