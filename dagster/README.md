# Dagster Pipeline

Orchestrates ingestion of stock minute aggregates from Massive S3 into the Iceberg lakehouse.

## Structure

```
pipelines/
├── definitions.py   # Entry point
├── resources.py     # MinIO, Massive S3, Spark Connect
├── jobs.py          # Backfill jobs (sequential/parallel)
├── sensors.py       # S3 file monitor
└── assets/
    └── bronze.py    # Bronze layer ingestion
```

## Running

```bash
# Development
uv run dagster dev

# Production
uv run dagster-webserver -h 0.0.0.0 -p 3000
```

## Jobs

| Job | Description |
|-----|-------------|
| `bronze_minute_aggs_job` | Triggered by sensor for new files |
| `backfill_sequential_job` | Process files one at a time |
| `backfill_parallel_job` | Batch read via Spark (faster) |

## Environment Variables

```bash
# Lakehouse (MinIO)
MINIO_DOMAIN, MINIO_PORT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY

# Massive S3 (source data)
MASSIVE_ACCESS_KEY, MASSIVE_SECRET_KEY

# Spark Connect
SPARK_HOST, SPARK_PORT
```
