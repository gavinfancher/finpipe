---
title: why stage parquet before writing to iceberg
date: 2026-03-29
summary: writing directly to iceberg from 30 concurrent threads is a recipe for metadata conflicts and tiny files. the two-phase approach solves both.
---

iceberg uses optimistic concurrency control for metadata commits. if 30 threads try to append to the same table simultaneously, you'll hit constant retry loops as each commit invalidates the others.

worse, each thread would write its own small file — thousands of tiny parquet files that destroy query performance. iceberg's metadata overhead per file compounds the problem.

the solution: stage first, commit second. phase 1 writes parquet files to a staging prefix on s3 — no iceberg involvement, no metadata contention. phase 2 uses spark to read all staged files, sort into partitions, compute column statistics for predicate pushdown, and write optimally sized files (128–256 mb target) in a single atomic iceberg commit.

the temporary double storage is negligible — at ~60 gb total and a ~20 minute job window, the overlap costs fractions of a cent. staged files are deleted after the commit succeeds.
