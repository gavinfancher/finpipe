FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first for layer caching
COPY backend/pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Copy all application code
COPY backend/api/ api/
COPY backend/pipeline/ pipeline/
COPY backend/streaming/ streaming/
COPY backend/control/ control/
COPY backend/auth.py backend/config.py backend/db.py backend/logging_config.py ./

# Install the project itself
RUN uv sync --no-dev

# Default: API + WebSocket relay
CMD ["uv", "run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
