FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/workspace \
    DAGSTER_HOME=/opt/dagster/dagster_home

WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY common/pyproject.toml common/pyproject.toml
COPY common/common/__init__.py common/common/__init__.py
COPY dagster/pyproject.toml dagster/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml

RUN uv sync --frozen --no-dev --all-packages --no-install-workspace
RUN mkdir -p $DAGSTER_HOME

WORKDIR /workspace/dagster
EXPOSE 4000
