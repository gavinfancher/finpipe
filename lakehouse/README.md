# Lakehouse Infrastructure

Docker Compose stack implementing a modern data lakehouse with Apache Iceberg.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────┐      ┌─────────────┐      ┌───────────┐  │
│   │    MinIO    │◀────▶│   Nessie    │◀────▶│   Spark   │  │
│   │  (Storage)  │      │  (Catalog)  │      │ (Compute) │  │
│   └─────────────┘      └─────────────┘      └───────────┘  │
│         ▲                    ▲                    ▲         │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│   ┌─────────────────────────────────────────────────────┐  │
│   │                       Trino                          │  │
│   │                   (Query Engine)                     │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Services

| Service | Ports | Technology | Purpose |
|---------|-------|------------|---------|
| **MinIO** | 9000, 9001 | MinIO | S3-compatible object storage for Iceberg data files |
| **Nessie** | 19120 | Project Nessie | Iceberg catalog with Git-like branching and versioning |
| **Spark** | 15002, 8080 | Spark 3.5 + Iceberg 1.8 | Distributed compute engine with Spark Connect |
| **Trino** | 8085 | Trino 479 | Fast SQL query engine for analytics |

## Why These Technologies?

### Apache Iceberg

- **ACID transactions**: Safe concurrent writes from multiple jobs
- **Time travel**: Query historical snapshots for debugging
- **Schema evolution**: Add columns without rewriting data
- **Partition evolution**: Change partitioning strategy without migration
- **Hidden partitioning**: No partition columns in queries

### Nessie Catalog

- **Git-like versioning**: Branch, merge, and tag table states
- **Multi-table transactions**: Atomic commits across tables
- **Audit history**: Track who changed what and when

### Spark Connect

- **Client-server architecture**: Thin Python client, heavy lifting on server
- **Resource isolation**: Multiple clients share single Spark cluster
- **Simplified deployment**: No Spark installation on client machines

## Storage Layout

```
MinIO (s3://warehouse/)
└── iceberg/
    ├── bronze/
    │   └── minute_aggs/
    │       ├── metadata/           # Iceberg metadata files
    │       └── data/
    │           ├── date=2026-01-14/  # Partition directories
    │           ├── date=2026-01-15/
    │           └── ...
    └── silver/
        └── minute_aggs/
            ├── metadata/
            └── data/
                ├── date=2026-01-14/
                └── ...
```

## Resource Allocation

The Spark container is configured for heavy workloads:

| Resource | Value | Purpose |
|----------|-------|---------|
| Driver Memory | 24 GB | Large shuffles and aggregations |
| Container Limit | 28 GB | Headroom for JVM overhead |

Adjust in `docker-compose.yml` based on your host machine.

## Spark Configuration

Key settings in `spark/spark-defaults.conf`:

```properties
# Iceberg + Nessie integration
spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.catalog-impl=org.apache.iceberg.nessie.NessieCatalog

# S3 access for lakehouse storage
spark.hadoop.fs.s3a.endpoint=http://minio:9000
spark.hadoop.fs.s3a.path.style.access=true

# Per-bucket credentials for Massive S3 (source data)
spark.hadoop.fs.s3a.bucket.flatfiles.endpoint=https://files.massive.com
```

## Usage

### Start All Services

```bash
docker compose up -d

# Verify all containers are healthy
docker compose ps
```

### Access UIs

| Service | URL | Purpose |
|---------|-----|---------|
| MinIO Console | http://localhost:9001 | Browse storage, manage buckets |
| Spark UI | http://localhost:8080 | Monitor jobs and executors |
| Trino UI | http://localhost:8085 | Query history and cluster status |
| Nessie | http://localhost:19120 | REST API for catalog operations |

### Query with Trino

```bash
docker exec -it trino trino

trino> USE iceberg.bronze;
trino> SELECT COUNT(*) FROM minute_aggs WHERE date = '2026-01-14';
trino> SELECT ticker, AVG(close) FROM minute_aggs GROUP BY ticker LIMIT 10;
```

### Connect PySpark Client

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder.remote("sc://localhost:15002").getOrCreate()
df = spark.table("iceberg.bronze.minute_aggs")
df.filter("date = '2026-01-14'").show()
```

## Maintenance

### View Iceberg Table History

```sql
-- In Trino
SELECT * FROM iceberg.bronze."minute_aggs$history";
SELECT * FROM iceberg.bronze."minute_aggs$snapshots";
```

### Compact Small Files

```sql
-- In Spark SQL
CALL iceberg.system.rewrite_data_files('bronze.minute_aggs');
```

### Expire Old Snapshots

```sql
CALL iceberg.system.expire_snapshots('bronze.minute_aggs', TIMESTAMP '2026-01-01');
```

## Volumes

Data persists in `./data/`:

| Directory | Contents |
|-----------|----------|
| `data/minio/` | Object storage files |
| `data/nessie/` | Catalog metadata (RocksDB) |
