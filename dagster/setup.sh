#!/bin/bash
set -e

echo "🚀 Setting up finpy-dagster..."

# Install uv if missing
if ! command -v uv &>/dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install deps
uv sync

# Setup config
[ -f .env ] || cp env.example .env

echo ""
echo "✅ Done! To run:"
echo "   uv run dagster dev --host 0.0.0.0"
