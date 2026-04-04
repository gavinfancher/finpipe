---
title: data ingestion
order: 1
category: architecture
summary: concurrent Python workers on EC2 spot instances download, decompress, and stage historical data as parquet on S3 — then Spark commits it to Iceberg.
---

the batch ingestion layer backfills historical equity and options data from the Massive API into the lakehouse. a full year backfill covers 200+ individual `.csv.gz` files.

### why EC2 + Python, not Spark

the bottleneck is network I/O — downloading compressed files from an external API. `ThreadPoolExecutor` with ~30 workers achieves real concurrency here because Python's GIL releases during I/O waits. Spark would add JVM overhead with no benefit for this workload.

network-optimized `c5n` instances provide up to 25 Gbps throughput. spot instances cut cost ~70% — the job is fault-tolerant since staged files in S3 survive interruptions.

### pipeline

1. concurrent workers download `.csv.gz` files from the Massive API
2. each file is decompressed via streaming gzip and parsed directly into PyArrow (never pandas)
3. columns are cast to the finpipe schema and written as parquet to `s3://bucket/bronze/staged/{ticker}/{date}.parquet`
4. once all files are staged, EMR Serverless runs a PySpark job to read the staged parquet, sort into partitions, and commit to Iceberg

### why staged writes before Iceberg

writing directly to partitioned Iceberg from 30 concurrent threads would risk metadata conflicts (Iceberg uses optimistic concurrency control) and produce thousands of tiny files. the two-phase approach lets Spark handle partition layout, column statistics for predicate pushdown, and optimal file sizing (128–256 MB per data file).
