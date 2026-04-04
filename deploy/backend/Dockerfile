FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy workspace root + dependency files first for layer caching
COPY pyproject.toml /workspace/pyproject.toml
COPY common/pyproject.toml /workspace/common/pyproject.toml
COPY common/common/__init__.py /workspace/common/common/__init__.py
COPY backend/pyproject.toml /workspace/backend/pyproject.toml

WORKDIR /workspace/backend
RUN uv sync --no-dev --no-install-project

# Copy shared library
COPY common/ /workspace/common/

# Copy all application code
COPY backend/api/ api/
COPY backend/core/ core/
COPY backend/streaming/ streaming/
COPY backend/tools/ tools/

# Install the project itself
RUN uv sync --no-dev

# Default: API + WebSocket relay
CMD ["uv", "run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
