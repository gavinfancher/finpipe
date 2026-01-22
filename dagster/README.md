# Dagster Pipeline

Orchestrates the ETL pipeline from Massive S3 → Bronze → Silver layers.


testing git workflows
## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dagster Orchestration                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐    │
│   │   Sensor    │─────▶│   Bronze    │─────▶│   Silver    │    │
│   │ (S3 watch)  │      │  (ingest)   │      │ (transform) │    │
│   └─────────────┘      └─────────────┘      └─────────────┘    │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              Backfill Jobs (manual trigger)              │  │
│   │  • backfill_sequential_job - reliable, slower           │  │
│   │  • backfill_parallel_job   - optimized, 5-10x faster    │  │
│   │  • silver_ticker_job       - single ticker/date         │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
pipelines/
├── definitions.py   # Dagster entry point - loads all assets, jobs, sensors
├── resources.py     # Configurable resources (Spark, MinIO, Massive S3)
├── jobs.py          # Backfill jobs with parallel Spark optimization
├── sensors.py       # S3 file monitor for incremental ingestion
└── assets/
    ├── bronze.py    # Raw data ingestion from Massive S3
    └── silver.py    # Data transformation and enrichment
```

## Assets

### Bronze Layer (`bronze.minute_aggs`)

Ingests raw minute aggregate data from Massive S3 into Iceberg.

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | string | Stock symbol (AAPL, MSFT, etc.) |
| `window_start` | long | Unix timestamp in nanoseconds |
| `open`, `high`, `low`, `close` | double | OHLC prices |
| `volume` | long | Shares traded |
| `transactions` | long | Number of trades |
| `date` | string | Partition key (YYYY-MM-DD) |

### Silver Layer (`silver.minute_aggs`)

Transforms bronze data with enrichments for analytics.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | timestamp | Human-readable datetime (Eastern Time) |
| `session` | string | `premarket`, `market`, `postmarket`, or `closed` |
| `rolling_15m_avg_close` | double | 15-bar rolling average of close price |
| `rolling_15m_avg_volume` | double | 15-bar rolling average of volume |
| `rolling_15m_high` | double | 15-bar rolling high |
| `rolling_15m_low` | double | 15-bar rolling low |
| `rolling_15m_total_volume` | long | 15-bar cumulative volume |

**Transformation logic:**
- Converts nanosecond epoch to Eastern Time using `from_utc_timestamp`
- Classifies trading session based on time of day
- Computes rolling window metrics partitioned by ticker+date (no cross-day leakage)

## Jobs

### `backfill_sequential_job`

Processes files one at a time. Reliable but slower.

```yaml
# Launchpad config
ops:
  backfill_sequential:
    config:
      prefix: "us_stocks_sip/minute_aggs_v1/2026/01/"
      overwrite: false
```

### `backfill_parallel_job`

**Optimized for performance.** Reads multiple files in a single Spark job.

```yaml
ops:
  backfill_parallel:
    config:
      prefix: "us_stocks_sip/minute_aggs_v1/2026/01/"
      batch_size: 0  # 0 = all files at once
      overwrite: false
```

**Why it's faster:**

| Aspect | Sequential | Parallel |
|--------|------------|----------|
| Spark jobs | N (one per file) | 1 |
| I/O pattern | Serial reads | Concurrent reads |
| Partitions | 1 per job | N (one per file) |
| Overhead | Job startup × N | Job startup × 1 |

For 20 files: Sequential ≈ 50 min, Parallel ≈ 5 min (**10x improvement**)

### `silver_ticker_job`

Transform a specific ticker/date combination. Useful for testing and targeted reprocessing.

```yaml
ops:
  build_silver_for_ticker:
    config:
      ticker: "AAPL"
      date: "2026-01-14"
```

## Sensors

### `massive_minute_aggs_sensor`

Monitors Massive S3 for new daily files.

- **Interval**: 60 seconds
- **Cursor**: Tracks last processed file key
- **Trigger**: Creates run request when new file detected

## Resources

All resources are configured via environment variables:

| Resource | Variables | Purpose |
|----------|-----------|---------|
| `spark` | `SPARK_HOST`, `SPARK_PORT` | Spark Connect client |
| `minio` | `MINIO_DOMAIN`, `MINIO_PORT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Lakehouse storage |
| `massive_s3` | `MASSIVE_ACCESS_KEY`, `MASSIVE_SECRET_KEY` | Source data access |

## Running

```bash
# Development (with UI at localhost:3000)
uv run dagster dev

# Production
uv run dagster-webserver -h 0.0.0.0 -p 3000 &
uv run dagster-daemon run &
```

## Testing a Backfill

1. Open Dagster UI → Jobs → `backfill_parallel_job`
2. Click **Launchpad**
3. Set prefix to desired month: `us_stocks_sip/minute_aggs_v1/2026/01/`
4. Click **Launch Run**
5. Monitor progress in the Runs tab
