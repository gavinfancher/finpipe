# finpipe

Real-time financial data platform — live equity streaming, historical backfill, and a lakehouse on AWS.

**[finpipe.app](https://finpipe.app)** — try the live dashboard

## what it does

- Streams live equity prices from the Massive API (formerly Polygon) over WebSocket
- Enriches ticks with daily change, 5d/1m/3m/6m/1y/YTD/3y performance (Fidelity-standard calendar conventions)
- Broadcasts enriched data to connected clients in real time
- Backfills historical data into Apache Iceberg on S3 for analytical queries
- Serves a React dashboard with live watchlists, positions, and market status

## architecture

```
                         ┌────────────────────┐
                         │   Cloudflare Pages  │
                         │   (finpipe.app)     │
                         └────────┬───────────┘
                                  │
                         ┌────────▼───────────┐
                         │  Cloudflare Tunnel  │
                         │  (api.finpipe.app)  │
                         └────────┬───────────┘
                                  │
┌─────────────────────────────────▼──────────────────────────────────┐
│ EC2 (Docker Compose)                                               │
│                                                                    │
│  ┌──────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────────────┐ │
│  │ ws-relay │  │ control │  │ ingest  │  │ Redpanda (Kafka)     │ │
│  │ FastAPI  │  │ ticker  │  │ Massive │  │                      │ │
│  │ + WS     │◄─┤ assign  │  │ API →   ├─►│ market-ticks topic   │ │
│  │          │  │         │  │ Redpanda│  │                      │ │
│  └────┬─────┘  └─────────┘  └─────────┘  └──────────────────────┘ │
│       │                                                            │
└───────┼────────────────────────────────────────────────────────────┘
        │
   ┌────▼──────────┐    ┌──────────────────┐
   │ RDS PostgreSQL │    │ ElastiCache      │
   │ (users, auth)  │    │ Valkey (Redis)   │
   └────────────────┘    │ (tick cache,     │
                         │  perf refs)      │
                         └──────────────────┘
```

### data tiers

| Tier | Store | Coverage |
|------|-------|----------|
| Hot  | Valkey (ElastiCache) | Latest tick per ticker + perf references |
| Cold | Apache Iceberg on S3 | Full historical |

## tech stack

| Layer | Technology |
|-------|------------|
| API + WebSocket | Python, FastAPI, uvicorn |
| Message bus | Redpanda (Kafka-compatible) |
| Cache | Valkey (Redis-compatible) on ElastiCache |
| Database | PostgreSQL on RDS |
| Orchestration | Dagster |
| Table format | Apache Iceberg |
| Batch compute | EMR Serverless (PySpark) |
| In-memory format | PyArrow |
| Frontend | React, TypeScript, Vite |
| Hosting | AWS (EC2, RDS, ElastiCache, S3) |
| CDN + tunnel | Cloudflare (Pages, Tunnel) |
| CI/CD | GitHub Actions |
| Package mgmt | uv |

## repo structure

```
finpipe/
├── backend/        # FastAPI API, WebSocket relay, ingest workers, control node
│   ├── api/        #   REST endpoints (auth, tickers, positions, market status)
│   ├── core/       #   enrichment, state, auth, DB
│   ├── streaming/  #   relay, ingest, control
│   └── tools/      #   seed_redis, migrations
├── common/         # shared schemas, trading calendar, Redis keys
├── dagster/        # batch ingestion jobs (backfill, close-of-day)
├── deploy/         # deployment configs (see deploy/README.md)
│   ├── docker/     #   Dockerfiles (streaming, dagster)
│   ├── ec2/        #   EC2 docker-compose + cloudflared
│   └── local/      #   local dev docker-compose
├── infra/          # AWS resource provisioning (boto3)
│   ├── ec2/        #   control node + backfill spot instances
│   ├── rds/        #   PostgreSQL
│   └── valkey/     #   ElastiCache
└── frontend/       # React/TypeScript SPA (Vite, Cloudflare Pages)
```

## local dev

requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node.js.

```bash
uv sync                # install Python deps (workspace)
cd frontend && npm i   # install frontend deps

make local-dev-up      # SSH tunnel to AWS, backend containers, frontend
make local-dev-down    # tear down
```

## deploy

push to `main` — GitHub Actions builds the frontend to Cloudflare Pages and deploys the backend to EC2 automatically.
