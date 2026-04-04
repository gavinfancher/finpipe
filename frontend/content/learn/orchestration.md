---
title: orchestration
order: 4
category: architecture
summary: Dagster manages batch backfills and close-of-day jobs. the NYSE calendar drives market-aware scheduling and ingest scaling.
---

Dagster manages the pipeline lifecycle — both batch backfills and recurring close-of-day jobs.

### close-of-day job

runs daily at 20:30 ET (after post-market closes) on a cron schedule. for every tracked ticker, it:

1. computes reference trading dates using the NYSE calendar (calendar offsets from the last trading day, matching Fidelity/Bloomberg conventions)
2. fetches closing prices from the Massive REST API for each reference date
3. writes a single Redis hash per ticker with the current price, daily change, all 7 performance percentages, and the 7 reference closes for live recomputation

this means the next morning's dashboard loads instantly from pre-computed Redis data — no API calls needed at startup.

### backfill job

provisions an EC2 spot instance, runs the concurrent ingestion pipeline, triggers the EMR Serverless Iceberg commit, and terminates the instance when complete. the entire workflow is a single Dagster graph with proper dependency tracking.

### market awareness

the control node uses `pandas_market_calendars` for the NYSE calendar, which includes all US holidays (MLK, Good Friday, Thanksgiving, etc.) and early close days. this drives both the ingest scaling (zero workers outside trading hours) and the market status API that the frontend consumes.
