# finpipe

Financial data platform for ingesting, processing, and streaming equity market data.

## Architecture

```
Massive API (.csv.gz)
    |
    v
EC2 Spot (concurrent Python workers)
    |
    v
Staged Parquet on S3
    |
    v
EMR Serverless (PySpark) --> Apache Iceberg (partitioned by date, ticker)
    |
    v
Trino / Athena
```

Real-time streaming runs in parallel — connecting to Massive WebSocket for live tick data, enriching with historical context, and broadcasting to the UI over WebSocket.

## Structure

```
finpipe/
├── dagster/     # Batch ingestion pipelines and EC2 provisioning
├── deploy/      # Dagster deployment on AWS (Docker, GitHub Actions)
├── stream/      # Real-time equity streaming platform
└── ui/          # React SPA (Cloudflare Pages)
```

### dagster/

Batch ingestion of historical equity and options data from the Massive API into Iceberg on S3.

- **main.py** — concurrent file download, streaming decompression, PyArrow parsing, parquet staging to S3
- **dagster_backfill.py** — Dagster job that provisions an EC2 spot instance via SSM, runs the backfill, and terminates
- **prov.py** — SSH-based EC2 provisioning (alternative to SSM)
- **setup_aws.py** — one-time IAM role, security group, and Secrets Manager setup

```bash
# one-time AWS setup
uv run python setup_aws.py

# run backfill via Dagster
uv run dagster dev -f dagster_backfill.py

# or run directly
uv run python main.py --year 2026 --months 3 --mode concurrent --workers 16
```

### deploy/

Dagster deployment stack for AWS EC2.

- Docker Compose with 4 services: PostgreSQL, code server, webserver, daemon
- GitHub Actions workflow for SSH-based deploys on push to main

### stream/

Real-time equity price streaming platform. Three services:

| Service    | Port | Description                                      |
|------------|------|--------------------------------------------------|
| Ingestion  | 9000 | Connects to Massive WebSocket, normalizes ticks  |
| API        | 8080 | FastAPI — auth, enrichment, WebSocket broadcast   |
| UI         | 5173 | Vite dev server (stream-specific dashboard)      |

Supporting infrastructure via Docker Compose: PostgreSQL, Prometheus, Loki, Grafana.

```bash
# start infrastructure
docker compose up -d

# start all services
uv run python main.py
```

Requires a `.env` file — see `.env.example` for required variables.

### ui/

Unified React/TypeScript SPA built with Vite. Target deployment: Cloudflare Pages.

Pages: Home, Dashboard, Faucet (live streaming), Analyst, Icehouse, Weather.

```bash
npm install
npm run dev
```

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# install all Python dependencies (uv workspace)
uv sync

# install UI dependencies
cd ui && npm install
```

The repo uses a uv workspace — `dagster/`, `deploy/`, and `stream/` are workspace members sharing a single lockfile.

## Branches

| Branch              | Description                                              |
|---------------------|----------------------------------------------------------|
| `main`              | Current monorepo                                         |
| `legacy/lakehouse`  | Previous architecture (local Spark, MinIO, Nessie, Trino)|
