# finpy

Stock market data pipeline using Dagster, Spark, and Iceberg.

## Architecture

```
Massive S3 (source) → Spark Connect → Iceberg (MinIO) → Trino (query)
                          ↑
                       Dagster (orchestration)
```

## Components

| Directory | Purpose |
|-----------|---------|
| `dagster/` | Pipeline orchestration (sensors, jobs, assets) |
| `lakehouse/` | Docker infrastructure (Spark, MinIO, Nessie, Trino) |
| `tests/` | Integration tests |

## Quick Start

```bash
# Start lakehouse infrastructure
cd lakehouse
docker compose up -d

# Run Dagster
cd ../dagster
uv run dagster dev
```

## Data Flow

1. **Sensor** monitors Massive S3 for new minute aggregate files
2. **Spark** reads CSV from Massive S3, writes to Iceberg (partitioned by date)
3. **Trino** provides SQL query access to Iceberg tables
