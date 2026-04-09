# finpipe

Real-time equity streaming, historical lakehouse ingestion, and a browser dashboard—wired together on AWS with a Cloudflare edge.

**[finpipe.app](https://finpipe.app)** — live dashboard (watchlists, positions, streaming quotes)

The API and WebSocket endpoint for production are served through **[api.finpipe.app](https://api.finpipe.app)** via Cloudflare Tunnel to the backend on EC2.

### Cloud migration (in progress)

Infrastructure and deploy docs skew toward the **current** shape: Docker Compose on a single EC2 “control” host (streaming services, Redpanda, tunnel, Dagster) plus managed RDS, Valkey, and S3/Iceberg/EMR for batch.

Work is underway to **split and scale** that footprint— notably ingest moving toward **ECS Fargate** when `ECS_CLUSTER` / `ECS_SERVICE` are configured: the control service can scale the ingest service’s desired task count based on ticker load (see `[backend/streaming/control.py](backend/streaming/control.py)`). Until cutover is complete, some diagrams and Make/CI paths still assume the EC2 compose stack; treat them as the live baseline, not the final form.

---

## What this repo contains


| Area               | Role                                                                                                                                                                                          |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Streaming**      | Massive (formerly Polygon) WebSocket → ingest workers → Redpanda → `ws-relay` enriches ticks and serves REST + WebSocket to clients.                                                          |
| **Control plane**  | Assigns tickers to ingest nodes; coordinates via PostgreSQL + Valkey (Redis-compatible).                                                                                                      |
| **Lakehouse**      | Dagster jobs: backfill from Massive flat files, staged Parquet on S3, EMR Serverless PySpark into **Apache Iceberg** (Glue catalog), queryable with Athena-style tooling.                     |
| **Frontend**       | React + TypeScript + Vite SPA: live stream UI, auth, learn/blog content from markdown.                                                                                                        |
| **Infra & deploy** | Boto3 scripts under `infra/` for AWS resources; Docker Compose on EC2 under `deploy/ec2/` (today’s primary deploy path: streaming stack, tunnel, Dagster)—evolving as the migration proceeds. |


---

## Architecture (high level)

**Real time**

```text
Browser (finpipe.app)
       │  WSS / HTTPS
       ▼
Cloudflare Tunnel ──► EC2 Docker Compose (baseline today)
                        ├── ws-relay (FastAPI + consumer + enrich)
                        ├── control (ticker assignment + optional ECS ingest scaling)
                        ├── ingest (Massive → Kafka; may run here or on ECS Fargate)
                        ├── Redpanda (+ console UI)
                        └── cloudflared
       ┌────────────────┴────────────────┐
       ▼                                 ▼
RDS PostgreSQL                    ElastiCache Valkey
(users, lists, positions)         (cache, perf refs, pub/sub)
```

**Batch / analytics**

```text
Massive API (.csv.gz)
       ▼
EC2 Spot workers (Python + PyArrow) → S3 staged Parquet
       ▼
EMR Serverless (PySpark) → Iceberg tables on S3 (Glue)
       ▼
Athena / Trino-class queries over Iceberg
```

Dagster (webserver, daemon, code location) currently runs alongside the streaming stack on the same EC2 host in compose; orchestration details live in `[dagster/README.md](dagster/README.md)` (placement may move as migration finishes).

---

## Repository layout

```text
finpipe/
├── backend/           # FastAPI app, WebSocket relay, ingest, control
│   ├── api/           # REST: auth, tickers, positions, market, health
│   ├── core/          # config, auth, DB, enrichment, state
│   ├── streaming/     # relay, ingest, control entrypoints
│   └── tools/         # e.g. seed_redis, SQL migrations
├── common/            # Shared Python: schemas, market calendar, Redis keys
├── dagster/           # Assets, jobs (backfill, close-of-day), sensors, Spark drivers
├── deploy/
│   ├── docker/        # Dockerfiles (streaming, Dagster)
│   ├── ec2/           # Production compose, tunnel config, setup
│   └── local/         # Local dev compose + env template
├── infra/             # One-off AWS provisioning (EC2, RDS, Valkey, S3, EMR, Glue, …)
└── frontend/          # Vite React app (see frontend/README.md)
```

---

## Tech stack


| Layer              | Choices                                                                     |
| ------------------ | --------------------------------------------------------------------------- |
| API + WebSocket    | Python 3.12+, FastAPI, uvicorn                                              |
| Messaging          | Redpanda (Kafka protocol)                                                   |
| Hot cache          | Valkey on ElastiCache                                                       |
| App database       | PostgreSQL on RDS                                                           |
| Orchestration      | Dagster                                                                     |
| Warehouse format   | Apache Iceberg on S3, Glue catalog                                          |
| Batch compute      | EMR Serverless (PySpark); ingestion workers on EC2 Spot                     |
| In-memory columnar | PyArrow                                                                     |
| Frontend           | React, TypeScript, Vite                                                     |
| Edge / tunnel      | Cloudflare (Pages for static UI, Tunnel for `api.finpipe.app`)              |
| Python tooling     | [uv](https://docs.astral.sh/uv/) workspace (`backend`, `dagster`, `common`) |


---

## Local development

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js, Docker, and SSH access configured for your environment (the Makefile assumes a specific EC2 key path and discovers the streaming instance by tag—adjust for your machine).

```bash
uv sync                      # Python workspace at repo root
cd frontend && npm install   # Frontend deps
```

Typical full stack (tunnels through EC2 to real RDS + Valkey, then local containers + Vite):

```bash
make local-dev-up      # SSH tunnels + docker compose + npm run dev (background)
make local-dev-down
```

- Frontend dev server: `http://localhost:5173`
- Backend (compose): `http://localhost:8080`
- Redpanda Console: `http://localhost:8888`

Database-only tunnels (e.g. psql, redis-cli, GUI clients):

```bash
make aws-db-up
make aws-db-down
```

Copy `deploy/local/.env.example` to `deploy/local/.env` and fill in secrets as needed. More detail: `[deploy/README.md](deploy/README.md)`.

---

## CI and deployment


| Workflow                                                       | Purpose                                                                                                                                                                                 |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[.github/workflows/ci.yml](.github/workflows/ci.yml)`         | On PR / push to `main` (excluding `frontend/**` and `**.md`): sync Dagster workspace and `dagster definitions validate`.                                                                |
| `[.github/workflows/deploy.yml](.github/workflows/deploy.yml)` | On push to `main` (same path ignores) or manual dispatch: SSH to EC2, `git pull`, conditional Docker Compose rebuild/restart for streaming, Dagster, tunnel, Spark script upload to S3. |


The deploy workflow does **not** build the frontend; production static assets for finpipe.app are expected to be published separately (e.g. Cloudflare Pages / `wrangler`—see `[frontend/README.md](frontend/README.md)`).

---

## Further reading

- `[deploy/README.md](deploy/README.md)` — EC2 compose, secrets, tunnel, Make targets  
- `[infra/README.md](infra/README.md)` — provisioning order for AWS resources  
- `[backend/README.md](backend/README.md)` — streaming service design  
- `[dagster/README.md](dagster/README.md)` — lakehouse pipeline and backfill strategy  
- `[common/README.md](common/README.md)` — shared library notes

