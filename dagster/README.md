# Finpipe — Bulk Historical Ingestion Pipeline

## Project Overview

This project ingests historical equity and options data from the **Massive API** (formerly Polygon) into a **data lakehouse backed by Apache Iceberg on AWS S3**. The goal is to backfill up to a full year of data (200+ individual `.csv.gz` files) efficiently and at low cost, with proper Iceberg partitioning for downstream query performance.

This is a **portfolio project** by Gavin Fancher, a Data Science student at UW-Madison graduating May 2026, targeting entry-level data engineering roles. The codebase should demonstrate production-grade DE patterns and be explainable in interviews.

---

## Architecture

### High-Level Flow

```
Massive API (.csv.gz files)
    ↓
EC2 Spot Instance — c5n.2xlarge or c5n.4xlarge (network-optimized)
    → Concurrent Python workers (ThreadPoolExecutor, ~30 workers)
    → Download .csv.gz → decompress → parse to PyArrow → write parquet
    → s3://bucket/bronze/staged/{ticker}/{date}.parquet
    ↓
EMR Serverless (PySpark)
    → Reads staged parquet from S3
    → Schema casting, column normalization
    → Writes to Iceberg partitioned by (date, ticker)
    → s3://bucket/iceberg/bronze/equities/
    ↓
Cleanup
    → Delete s3://bucket/bronze/staged/ prefix
    ↓
Trino / Athena
    → Query layer over Iceberg tables
```

### Why This Architecture

- **EC2 + Python (not Spark) for ingestion**: The bottleneck is network I/O (downloading files), not compute. `ThreadPoolExecutor` achieves real concurrency for I/O-bound workloads because Python's GIL releases during I/O waits. Spark would add JVM overhead with no benefit at this stage.
- **Network-optimized EC2**: `c5n` series has up to 25 Gbps network throughput — critical when pulling 200+ files from an external API.
- **Spot instance**: This is a fault-tolerant batch job. If interrupted, staged files in S3 survive and the job can resume. Spot cuts cost ~70%.
- **Staged parquet first, Iceberg second**: Writing directly to partitioned Iceberg from 30 concurrent threads risks metadata conflicts (Iceberg uses optimistic concurrency control) and produces thousands of tiny files. Spark handles the Iceberg write properly — sorts into partitions, computes column statistics (min/max for predicate pushdown), writes optimally sized files (128–256 MB target).
- **EMR Serverless (not EMR cluster)**: No persistent cluster to manage. Pay per vCPU-second only while the job runs. Works here because all data is already in S3 — EMR Serverless can't reach the public internet, but it doesn't need to.
- **Partitioned by (date, ticker)**: Enables partition pruning. A downstream job reading AAPL for Q1 2024 scans only the relevant partitions, not the full table.

### Storage Cost Note

Temporary double storage during the staged → Iceberg window is negligible. At ~60 GB total and a ~20 minute job window, the cost of the overlap is fractions of a cent. Staged files are deleted after the Iceberg commit.

---

## Tech Stack


| Layer             | Technology                              |
| ----------------- | --------------------------------------- |
| Cloud             | AWS                                     |
| Object Storage    | S3                                      |
| Table Format      | Apache Iceberg                          |
| Iceberg Catalog   | AWS Glue Data Catalog                   |
| Ingestion Compute | EC2 Spot (c5n.2xlarge / c5n.4xlarge)    |
| Transform Compute | EMR Serverless (PySpark)                |
| In-memory format  | PyArrow (never pandas)                  |
| Concurrency       | `concurrent.futures.ThreadPoolExecutor` |
| Query Layer       | Trino / Amazon Athena                   |
| Data Source       | Massive API (formerly Polygon)          |


---

## Data Source

- **Massive API** provides flat files for historical equities and options data as `.csv.gz`
- Files are organized by ticker and date
- A full year backfill = 200+ individual files
- Equities: minute-bar OHLCV + transactions
- Options: Greeks, IV surface, GEX-relevant fields

### Finpipe Schema Convention

Primary timestamp column: `window_start` (nanosecond epoch)
Standard columns: `window_start`, `open`, `high`, `low`, `close`, `volume`, `transactions`, `date`, `ticker`, `session`

---

## Phase 1 — EC2 Concurrent Ingestion

### Key Implementation Details

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, gzip, io
import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq

def process_file(file_meta):
    # 1. Download .csv.gz from Massive API
    resp = requests.get(file_meta.url, stream=True)
    
    # 2. Decompress + parse directly to Arrow (never pandas)
    with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
        arrow_table = pa_csv.read_csv(gz)
    
    # 3. Cast/rename columns to match Finpipe schema
    arrow_table = cast_to_schema(arrow_table)
    
    # 4. Write staged parquet to S3 bronze raw zone
    s3_path = f"s3://bucket/bronze/staged/{file_meta.ticker}/{file_meta.date}.parquet"
    pq.write_table(arrow_table, s3_path)
    
    return s3_path

# ~30 concurrent workers — cap to respect Massive API rate limits
with ThreadPoolExecutor(max_workers=30) as executor:
    futures = {executor.submit(process_file, f): f for f in file_list}
    staged_paths = []
    for future in as_completed(futures):
        try:
            staged_paths.append(future.result())
        except Exception as e:
            # log and continue — don't fail the whole batch
            print(f"Failed: {e}")
```

### Concurrency Notes

- **ThreadPoolExecutor is appropriate here** because the workload is I/O-bound (network download + S3 upload). The GIL releases during I/O waits so threads achieve real parallelism.
- If transforms were CPU-heavy (ML inference, complex math), `multiprocessing` would be needed instead.
- Use exponential backoff on Massive API calls — rate limits are real.
- Cap at 20–30 workers; more doesn't help if you're hitting API rate limits.

---

## Phase 2 — EMR Serverless Spark → Iceberg

### Key Implementation Details

```python
# PySpark job submitted to EMR Serverless
df = spark.read.parquet("s3://bucket/bronze/staged/")

# Schema normalization
df = cast_and_rename(df)

# Write to Iceberg with proper partitioning
df.writeTo("glue.bronze.equities_raw") \
  .partitionedBy("date", "ticker") \
  .append()
```

### Iceberg Spark Config

```python
spark = SparkSession.builder \
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .config("spark.sql.catalog.glue", "org.apache.iceberg.aws.glue.GlueCatalog") \
    .config("spark.sql.catalog.glue.warehouse", "s3://bucket/iceberg/") \
    .config("spark.sql.catalog.glue.io-impl", "org.apache.iceberg.aws.s3.S3FileIO") \
    .getOrCreate()
```

### EMR Serverless Constraints

- **No public internet access** — all data must already be in S3 before the job runs. This is by design in this architecture (Phase 1 handles all external API calls).
- Dependencies must be bundled with the job or pre-staged in S3 (no `pip install` at runtime).
- Cold start: ~2–3 minutes to provision workers. Acceptable for batch jobs, not for interactive use.
- Logs go to S3 and CloudWatch — no SSH access.

---

## Phase 3 — Cleanup

After the Iceberg commit succeeds:

```bash
aws s3 rm s3://bucket/bronze/staged/ --recursive
```

Only run after verifying the Iceberg table registered correctly (row count check, partition count check).

---

## Broader Finpipe Context

This ingestion pipeline feeds into the larger Finpipe platform:

- **Finpipe** is a self-hosted financial data platform originally on Proxmox homelab, being extended to AWS
- Full stack includes: Python/Go ingestion, Dagster orchestration, Apache Spark, Apache Iceberg, MinIO (S3-compatible on-prem), Redpanda (Kafka-compatible), Valkey (Redis-compatible), TimescaleDB, Trino, FastAPI backend, React/TypeScript/Vite frontend
- This AWS pipeline is the **batch/historical layer** of that platform
- Real-time equity streaming uses a separate Go-based service (`finpipe-faucet`) with WebSocket feed from Massive API
- MCP natural language query interface connects to Claude Desktop for querying the lakehouse

### Data Tiering


| Tier | Store               | Coverage            |
| ---- | ------------------- | ------------------- |
| Hot  | Valkey              | Last 30 minutes     |
| Warm | TimescaleDB         | Last 5 trading days |
| Cold | Iceberg on S3/MinIO | Full historical     |


---

## Interview Talking Points

Key architectural decisions to be able to explain:

1. **EC2 over Spark for ingestion** — bottleneck is network I/O not compute; Spark adds JVM overhead with no benefit; right tool for the job
2. **ThreadPoolExecutor over asyncio** — downloads + decompression + Arrow parsing are blocking operations; threads are more appropriate than async here
3. **PyArrow over pandas** — faster, more memory efficient, native parquet/Iceberg compatibility
4. **Staged writes before Iceberg commit** — avoids OCC metadata conflicts from concurrent writers; avoids tiny files problem; atomic commit
5. **Spark for the Iceberg write** — handles partition layout, column statistics (predicate pushdown), optimal file sizing (128–256 MB)
6. **Partition by (date, ticker)** — enables partition pruning; downstream jobs reading a single ticker scan only relevant partitions
7. **Glue Catalog** — native AWS, free at this scale, works with both Athena and EMR Serverless out of the box
8. **Spot instance** — job is fault-tolerant (staged files survive interruption), Spot cuts cost ~70%
9. **EMR Serverless over persistent cluster** — no idle cluster cost, pay per vCPU-second, appropriate for scheduled batch jobs

---

## Open Questions / TODOs

- Massive API rate limit — confirm exact limits and adjust `max_workers` accordingly
- Schema mapping — confirm Massive flat file column names → Finpipe schema
- Options vs equities — may need separate Iceberg tables or unified schema with nullable columns
- Dagster integration — wire this pipeline into Dagster as a backfill job with `DynamicOutput`
- Incremental ingestion — after initial backfill, how to detect and ingest new files (date-based watermark)
- File size targets — tune Spark `coalesce` / `repartition` to hit 128–256 MB per Iceberg data file
- Glue Catalog setup — create database and table definitions before first write

