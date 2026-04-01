---
title: lakehouse
order: 2
---

staged parquet files are transformed via emr serverless (pyspark) and committed to apache iceberg tables on s3. iceberg provides acid transactions, partition pruning, and time travel. tables are partitioned by (date, ticker) and cataloged in aws glue.

the two-phase approach — stage first, iceberg commit second — avoids metadata conflicts from concurrent writers and ensures optimal file sizing (128–256 mb per data file).
