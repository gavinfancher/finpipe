FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Pre-install workspace deps into a venv that lives OUTSIDE /workspace, so the
# host bind-mount at /workspace does not shadow it. Code is mounted at runtime;
# rebuild this image only when uv.lock changes.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY dagster/pyproject.toml dagster/pyproject.toml

RUN uv sync --frozen --no-dev --all-packages --no-install-workspace

WORKDIR /workspace/backend
