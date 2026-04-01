---
title: data ingestion
order: 1
---

historical equity and options data is pulled from the massive api (polygon.io) as compressed csv files. concurrent python workers running on ec2 spot instances download, decompress via streaming gzip, parse with pyarrow (never pandas), and stage as parquet files on s3.

network-optimized c5n instances with ~30 threads handle the i/o-bound workload. spot instances cut cost ~70% — the job is fault-tolerant since staged files in s3 survive interruptions.
