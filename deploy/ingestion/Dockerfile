FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first for layer caching
COPY backend/pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Copy only streaming + control code
COPY backend/streaming/ streaming/
COPY backend/control/ control/

# Install the project itself
RUN uv sync --no-dev

# Default: ingestion node (override CMD in compose for control node)
CMD ["uv", "run", "python", "-m", "streaming.massive"]
