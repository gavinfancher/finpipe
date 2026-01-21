# finpy

A production-grade data lakehouse for US equities market data, built with modern data engineering best practices.

## Project Overview

This project implements a **medallion architecture** (Bronze → Silver → Gold) to ingest, transform, and serve high-frequency stock market data. The pipeline processes ~390 million minute-level price bars per month from Massive (formerly Polygon.io) flat files into an Apache Iceberg lakehouse.

### Key Technologies

| Layer | Technology | Purpose |
|-------|------------|---------|
| Orchestration | **Dagster** | Pipeline scheduling, monitoring, backfills |
| Compute | **Apache Spark 3.5** | Distributed data processing |
| Storage | **Apache Iceberg** | ACID-compliant table format with time travel |
| Object Store | **MinIO** | S3-compatible storage layer |
| Catalog | **Nessie** | Git-like versioning for Iceberg tables |
| Query | **Trino** | Ad-hoc SQL analytics |

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Massive S3     │────▶│  Spark Connect   │────▶│  Iceberg/MinIO  │
│  (Source Data)  │     │  (Compute)       │     │  (Lakehouse)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               ▲                         │
                               │                         ▼
                        ┌──────────────┐          ┌─────────────┐
                        │   Dagster    │          │    Trino    │
                        │ (Orchestrate)│          │   (Query)   │
                        └──────────────┘          └─────────────┘
```

## Medallion Architecture

| Layer | Table | Description |
|-------|-------|-------------|
| **Bronze** | `bronze.minute_aggs` | Raw minute bars, partitioned by date. Schema preserved from source. |
| **Silver** | `silver.minute_aggs` | Cleaned data with timestamps converted to ET, market session flags, 15-minute rolling metrics. |
| **Gold** | *(planned)* | Ticker-filtered aggregations, daily summaries, analytics-ready views. |

## Performance Optimizations

### Parallel Backfill Processing

The pipeline supports two backfill strategies with significantly different performance characteristics:

| Strategy | Implementation | Performance |
|----------|----------------|-------------|
| **Sequential** | Process files one-by-one in a loop | ~2-3 min/file (I/O bound) |
| **Parallel** | Spark reads multiple files simultaneously | **5-10x faster** |

**How parallel backfill works:**

```python
# Sequential: N files = N separate Spark jobs
for file in files:
    df = spark.read.csv(file)  # One file at a time
    df.writeTo(table).append()

# Parallel: N files = 1 Spark job with N partitions
df = spark.read.csv([file1, file2, ..., fileN])  # All files at once
df.writeTo(table).append()  # Single write operation
```

Spark's parallel read creates **one partition per input file**, allowing concurrent I/O across the cluster. For a 20-file backfill, this reduces wall-clock time from ~50 minutes to ~5 minutes.

### Iceberg Optimizations

- **Partition pruning**: Tables partitioned by `date` enable efficient filtering
- **Parquet + ZSTD**: Columnar format with high compression ratio (~10:1)
- **Hidden partitioning**: Iceberg manages partition columns transparently

## Project Structure

```
finpy/
├── dagster/              # Pipeline orchestration
│   ├── pipelines/
│   │   ├── assets/       # Bronze & Silver layer transformations
│   │   ├── jobs.py       # Backfill jobs (sequential/parallel)
│   │   ├── sensors.py    # S3 file monitors
│   │   └── resources.py  # Spark, MinIO, Massive S3 clients
│   └── pyproject.toml
├── lakehouse/            # Infrastructure
│   ├── docker-compose.yml
│   └── spark/            # Spark configuration
├── mcp/                  # MCP server for Claude Desktop integration
│   ├── server.py         # Query tools for LLM access
│   └── pyproject.toml
└── tests/
```

## Quick Start

```bash
# 1. Start lakehouse infrastructure
cd lakehouse
docker compose up -d

# 2. Configure environment
cd ../dagster
cp .env.example .env  # Add your Massive API keys

# 3. Run Dagster
uv run dagster dev
```

## Data Flow

1. **Sensor** polls Massive S3 hourly for new minute aggregate files
2. **Bronze ingestion** loads raw CSV into Iceberg with date partitioning
3. **Silver transformation** adds:
   - Timestamp conversion (nanoseconds → Eastern Time)
   - Market session classification (premarket/market/postmarket)
   - 15-minute rolling metrics (avg close, volume, high/low)
4. **Trino** provides SQL access for analytics and dashboards

## MCP Server (LLM Integration)

The `mcp/` directory contains an MCP server for querying data via Claude Desktop:

```
You: "Get me SPY for the last 3 days as parquet"
Claude: *calls export_parquet* → /tmp/finpy_exports/spy_2026-01-17_to_2026-01-20.parquet
```

See [mcp/README.md](mcp/README.md) for setup instructions.

## Skills Demonstrated

- **Data Lakehouse Architecture**: Medallion pattern with Iceberg tables
- **Distributed Computing**: Spark optimization for parallel I/O
- **Pipeline Orchestration**: Dagster assets, sensors, and jobs
- **Infrastructure as Code**: Docker Compose for reproducible environments
- **LLM Tool Integration**: MCP server for natural language data access
- **Modern Python**: Type hints, dataclasses, uv package management
