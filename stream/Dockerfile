FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Copy application code
COPY server/ server/

# Install the project itself
RUN uv sync --no-dev

# Default: API service (override CMD in compose for other services)
CMD ["uv", "run", "uvicorn", "server.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
