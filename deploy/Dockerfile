FROM ghcr.io/astral-sh/uv:latest AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /opt/dagster/app

COPY pyproject.toml uv.lock ./
COPY pipelines pipelines
RUN uv sync --frozen --no-dev --no-editable

ENV DAGSTER_HOME=/opt/dagster/dagster_home
RUN mkdir -p $DAGSTER_HOME

EXPOSE 4000
