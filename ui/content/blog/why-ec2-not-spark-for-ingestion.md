---
title: why ec2, not spark, for ingestion
date: 2026-03-29
summary: the bottleneck is network i/o, not compute. here's why threadpoolexecutor on a spot instance beats a spark cluster for downloading files.
---

when you're pulling 200+ compressed csv files from an external api, the bottleneck is network i/o — not compute. spark adds jvm overhead, cluster management, and driver coordination with zero benefit at this stage.

python's threadpoolexecutor achieves real concurrency for i/o-bound workloads because the gil releases during network waits. ~30 threads on a c5n instance (up to 25 gbps network throughput) saturate the connection without any of spark's complexity.

the key insight: match the tool to the bottleneck. spark is the right tool for the iceberg write phase where you need partition layout, column statistics, and optimal file sizing. but for downloading files? a simple thread pool wins.

spot instances make this even more compelling — the job is fault-tolerant (staged files survive interruption), and spot cuts cost ~70%. if the instance gets reclaimed, restart and pick up where you left off.
