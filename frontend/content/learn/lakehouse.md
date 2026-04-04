---
title: lakehouse
order: 2
category: architecture
summary: Apache Iceberg on S3 with AWS Glue catalog — ACID transactions, partition pruning, and time travel over plain object storage.
---

the cold storage tier is an Apache Iceberg lakehouse on S3, cataloged in AWS Glue.

### why Iceberg

Iceberg provides ACID transactions, schema evolution, partition pruning, and time travel over plain object storage. tables are partitioned by `(date, ticker)` — a downstream query for AAPL in Q1 2024 scans only the relevant partitions, not the full table.

### EMR Serverless

the Iceberg write runs on EMR Serverless (PySpark). there's no persistent cluster to manage — you pay per vCPU-second only while the job runs. this works because all data is already in S3 before the job starts. EMR Serverless can't reach the public internet, but it doesn't need to.

cold start is ~2–3 minutes to provision workers, which is acceptable for a batch job that runs once after ingestion completes.

### Glue Catalog

AWS Glue Data Catalog serves as the Iceberg catalog. it's native to AWS, free at this scale, and works with both Athena and EMR Serverless out of the box. downstream queries run through Trino or Amazon Athena.

### storage cost

temporary double storage during the staged-to-Iceberg window is negligible. at ~60 GB total and a ~20 minute job window, the cost of the overlap is fractions of a cent. staged files are deleted after the Iceberg commit succeeds.
