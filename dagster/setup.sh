#!/bin/bash
set -euo pipefail

# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# install deps
uv sync

echo ""
echo "ready — run with:"
echo "  uv run python main.py --year 2026 --months 3"
