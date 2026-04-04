---
title: overview
order: 0
category: overview
---

finpipe is a self-hosted financial data platform that ingests, processes, and serves equity market data in real time.

the platform connects to the Massive API (formerly Polygon) to stream live tick data, enriches it with historical performance metrics, and broadcasts it to connected clients over WebSocket. a batch pipeline backfills historical data into an Apache Iceberg lakehouse on S3 for analytical queries.

## what you're looking at

- **live streaming** — real-time equity prices with sub-second latency from market open to post-market close
- **performance enrichment** — every tick is enriched with daily change and 5d/1m/3m/6m/1y/YTD/3y performance using industry-standard calendar conventions (matches Fidelity/Bloomberg)
- **market-aware** — the backend serves holiday-aware market status using the NYSE calendar, so the UI shows correct session state even on holidays and early close days
- **hot cache** — a single Redis hash per ticker (20 fields) holds everything needed to render the dashboard instantly, even when the market is closed

## design goals

this is a portfolio project targeting entry-level data engineering roles. the codebase is designed to demonstrate:

- production-grade streaming architecture with proper separation of concerns
- cost-efficient AWS deployment (spot instances, serverless compute, managed services)
- real-time data enrichment with historical context
- clean infrastructure-as-code with boto3 provisioning scripts
