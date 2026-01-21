# Lakehouse Infrastructure

Docker Compose stack for the Iceberg lakehouse.

## Services

| Service | Port | Purpose |
|---------|------|---------|
| MinIO | 9000, 9001 | S3-compatible object storage |
| Nessie | 19120 | Iceberg catalog (Git-like versioning) |
| Spark | 15002, 8080 | Compute engine + Spark Connect |
| Trino | 8085 | SQL query engine |

## Usage

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f spark-iceberg

# Stop
docker compose down
```

## Storage Layout

```
MinIO (s3://warehouse/)
└── iceberg/
    └── bronze/
        └── minute_aggs/    # Partitioned by date
```

## Spark Connect

Remote PySpark clients connect to `spark-iceberg:15002`. The server has Massive S3 credentials configured for direct reads from `s3a://flatfiles/`.
