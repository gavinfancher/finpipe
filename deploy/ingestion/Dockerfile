FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first for layer caching
COPY ingestion/pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Copy application code
COPY ingestion/streaming/ streaming/
COPY ingestion/control/ control/
COPY ingestion/batch/ batch/

# Install the project itself
RUN uv sync --no-dev

# Default: ingestion node (override CMD in compose for control node)
CMD ["uv", "run", "python", "-m", "streaming.massive"]
