FROM ghcr.io/astral-sh/uv:latest AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /opt/dagster/app

# Copy dependency files first for layer caching
COPY common/pyproject.toml /common/pyproject.toml
COPY dagster/pyproject.toml ./

# Copy shared library
COPY common/ /common/

# Copy application code
COPY dagster/definitions.py ./
COPY dagster/jobs/ jobs/
COPY dagster/assets/ assets/
COPY dagster/resources/ resources/
COPY dagster/sensors/ sensors/
COPY dagster/transforms/ transforms/

RUN uv sync --no-dev --no-editable

ENV DAGSTER_HOME=/opt/dagster/dagster_home
RUN mkdir -p $DAGSTER_HOME

EXPOSE 4000
