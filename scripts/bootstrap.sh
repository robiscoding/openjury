#!/bin/bash

set -e

echo "🚀 Setting up OpenJury development environment..."

if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v make &> /dev/null; then
    echo "❌ make is not installed. Please install make first."
    exit 1
fi

echo "📦 Installing development dependencies..."
make install-dev

echo "🧹 Cleaning any existing build artifacts..."
make clean

echo "✅ Development environment setup complete!"
echo ""
echo "Available commands:"
echo "  make help      - Show all available commands"
echo "  make format    - Format code with Ruff"
echo "  make lint      - Run code quality checks"
echo "  make test      - Run tests"
echo "  make build     - Build distribution files"
echo "  make release   - Publish to PyPI (requires credentials)"
echo ""
echo "Quick development workflow:"
echo "  make dev       - Format code and run tests"
echo "  make check     - Run all quality checks" 