# Dagster Redesign Plan

## Context

The dagster pipeline has separation-of-concerns issues, incorrect logging patterns, missing resources, and doesn't follow dagster best practices. The UI logging/graphing doesn't work well because ops bypass `context.log` and create their own clients instead of using Dagster resources. The goal is to restructure so everything is visible, testable, and follows the asset-first paradigm.

## Problems Being Fixed

1. `close_of_day.py` uses `get_dagster_logger()` instead of `context.log` — logs don't show up properly in UI
2. `close_of_day.py` creates Redis, Postgres, and Massive REST clients via raw `os.environ` — not Dagster resources
3. `close_of_day.py` is modeled as ops+graph but produces materialized state (Redis cache) — should be assets
4. `emr.py` resource uses `get_dagster_logger()` instead of accepting context
5. `backfill.py` creates boto3 clients directly, not through resources
6. `fetch_and_cache_closes` is a 60-line monolith mixing API calls, math, and Redis writes
7. Backfill graph has incorrect dependency ordering (`teardown_spot` and `commit_to_iceberg` can run in parallel)
8. Business logic lives directly in ops/assets instead of separate modules

## Changes

### 1. Add missing Dagster resources

**File: `dagster/resources/redis.py`** (new)

- `RedisResource(ConfigurableResource)` wrapping a Redis connection
- Config: `url: str` with env fallback

**File: `dagster/resources/postgres.py`** (new)

- `PostgresResource(ConfigurableResource)` wrapping asyncpg
- Config: `database_url: str` with env fallback
- Method: `get_all_tickers()` using `common.postgres.get_all_tickers`

**File: `dagster/resources/massive_api.py`** (new)

- `MassiveAPIResource(ConfigurableResource)` wrapping the Massive REST client
- Config: `api_key: str` with env fallback
- Method: `get_client() -> RESTClient`

**File: `dagster/resources/__init__.py`** (edit)

- Add Redis, Postgres, MassiveAPI to `get_configured_resources()`
- Wire secrets for each

### 2. Fix EMR resource logging

**File: `dagster/resources/emr.py`** (edit)

- Remove `get_dagster_logger()` calls
- `submit_spark_job` and `wait_for_job` accept an optional `log` parameter (dagster context logger)
- When called from an asset/op, pass `context.log`; resource methods that need logging accept it explicitly

### 3. Convert close-of-day from ops+graph to assets

**File: `dagster/assets/close_of_day.py`** (new)

- `reference_closes` asset (group: `market_data`) — fetches reference close prices from Massive API, outputs structured data
- `ticker_cache` asset (group: `market_data`, deps: `reference_closes`) — computes perf percentages and writes to Redis
- Both use `context.log`, and receive Redis/Postgres/MassiveAPI as proper Dagster resources
- Extract perf calculation logic to a pure function in `common/common/market.py`

**File: `dagster/jobs/close_of_day.py`** (rewrite)

- `close_of_day_job = define_asset_job(name="close_of_day_job", selection=[...close of day assets...])`
- Keep the schedule definition pointing at the new asset job

### 4. Clean up backfill job

**File: `dagster/jobs/backfill.py`** (edit)

- Fix graph wiring: `commit_to_iceberg` must complete before `teardown_spot`
  ```
  instance_id → setup → run_staging → commit_to_iceberg → teardown_spot
  ```
- Replace inline `boto3.client()` calls with a lightweight helper or pass region as config
- Use `context.log` consistently (already mostly correct here, just the `log_ssm` helper)

### 5. Update definitions.py and **init** files

**File: `dagster/assets/__init__.py`** (edit)

- Add new close-of-day assets to `all_assets`

**File: `dagster/jobs/__init__.py`** (edit)

- Update imports for rewritten close_of_day_job

**File: `dagster/definitions.py`** — no changes needed (already wires everything via `all_*` lists)

### 6. Remove empty transforms/ directory

- Delete `dagster/transforms/__init__.py` and the directory

## File Change Summary


| File                               | Action                                    |
| ---------------------------------- | ----------------------------------------- |
| `dagster/resources/redis.py`       | **new**                                   |
| `dagster/resources/postgres.py`    | **new**                                   |
| `dagster/resources/massive_api.py` | **new**                                   |
| `dagster/resources/__init__.py`    | edit — add new resources                  |
| `dagster/resources/emr.py`         | edit — fix logging                        |
| `dagster/assets/close_of_day.py`   | **new** — asset-based replacement         |
| `dagster/assets/__init__.py`       | edit — add new assets                     |
| `dagster/jobs/close_of_day.py`     | rewrite — asset job + schedule only       |
| `dagster/jobs/__init__.py`         | edit — update imports                     |
| `dagster/jobs/backfill.py`         | edit — fix graph ordering, clean up boto3 |
| `dagster/transforms/`              | delete                                    |


## What This Does NOT Change

- `bronze_minute_aggs` and `silver_minute_aggs` assets — already well-structured
- `daily_ingest_sensor` — already correct (uses `context.log`, proper resource injection)
- `daily_lakehouse_job` — already correct (asset job)
- `batch/main.py` and `spark/` scripts — standalone, not Dagster-managed
- `common/` shared library — may add a small perf calculation helper

## Verification

1. `cd dagster && uv run dagster definitions validate` — confirms all definitions load without import errors
2. Check Dagster UI: new close-of-day assets should appear in the asset graph under `market_data` group
3. Check Dagster UI: backfill job graph should show linear dependency chain
4. Resources should all appear in the Dagster UI resources page (Redis, Postgres, MassiveAPI, MassiveS3, EMR)

