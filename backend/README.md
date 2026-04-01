# finpipe-stream

Real-time equity price streaming platform. Distributes market data from the Massive WebSocket feed across multiple ingestion nodes via Redpanda, enriches ticks with cached performance metrics from Redis, and serves live prices to a browser dashboard over WebSocket.

## Architecture

```
                        ┌──────────────┐
                        │  Massive API │
                        │  (WebSocket) │
                        └──┬───┬───┬───┘
                           │   │   │
              ┌────────────┤   │   ├────────────┐
              ▼            ▼       ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ ingest-0 │ │ ingest-1 │ │ ingest-2 │  ≤100 tickers each
        │          │ │          │ │          │  assigned by control
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             ▼            ▼            ▼
        ┌─────────────────────────────────┐
        │         Redpanda (Kafka)        │
        │      topic: market-ticks        │
        └────────────────┬────────────────┘
                         │
                         ▼
                ┌─────────────────┐
                │    ws-relay     │
                │  consume ticks  │──► Redis (enrich with perf data)
                │  enrich + serve │
                │  REST API + WS  │
                └────────┬────────┘
                         │ WebSocket
                         ▼
                ┌─────────────────┐
                │   React UI      │
                │  finpipe.app    │
                └─────────────────┘

        ┌──────────────┐
        │ Control Node │  polls PG for all tickers
        │              │  assigns tickers to ingest nodes
        │              │  publishes via Redis pub/sub
        └──────┬───────┘
               │
        ┌──────┴──────┐      ┌─────────────┐
        │    Redis     │      │  PostgreSQL  │
        │ assignments  │      │  users       │
        │ price cache  │      │  watchlists  │
        │ perf metrics │      │  positions   │
        └─────────────┘      │  preferences │
                              └─────────────┘

        ┌──────────────────┐
        │  Dagster          │
        │  close-of-day     │  20:30 NYC weekdays
        │  batch job        │  fetches reference closes
        └──────────────────┘
```

### Services (docker-compose)

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `postgres:17` | 5432 | Users, watchlists, positions, preferences |
| `redpanda` | `redpandadata/redpanda` | 9092 | Kafka-compatible message broker |
| `redis` | `redis:7-alpine` | 6379 | Ticker assignments, price cache, perf metrics |
| `control` | custom | - | Polls PG for tickers, distributes across ingest nodes |
| `ingest-0/1/2` | custom | - | Connect to Massive WS, produce to Redpanda |
| `ws-relay` | custom | 8080 | Consume from Redpanda, enrich, serve REST API + WS |

### Data flow

#### Tick lifecycle
```
Massive WebSocket
  → Ingest node (normalise A.SPY → SPY, produce to Redpanda)
  → ws-relay (consume from Redpanda)
  → enrich_tick() (Redis lookup: prev_close, perf refs)
      adds: change, changePct, prevClose, perf5d/1m/3m/6m/1y/ytd/3y
  → state.ticks updated
  → broadcast to all UI WebSocket clients
```

#### User adds a ticker
```
UI → POST /external/tickers/{ticker}
  → DB: insert into user_tickers
  → Response returns immediately
  → Background: fetch latest price + perf data from Massive REST API
  → Cache in Redis, update state.ticks
  → Broadcast to connected WS clients
  → Control node picks up new ticker on next poll (5s)
  → Assigns to an ingest node via Redis pub/sub
  → Ingest node subscribes to Massive WS feed
```

#### Control node assignment
```
Poll PostgreSQL every 5s for all unique tickers
  → Compute node count (min 3, always odd, ≤100 tickers/node)
  → Round-robin assign tickers to nodes
  → Write ticker:assignments hash to Redis
  → Publish per-node assignment lists via Redis pub/sub
  → Ingest nodes update their Massive WS subscriptions
```

#### Off-hours / weekend
```
ws-relay startup:
  → load_all_cached_ticks() from Redis
  → Pre-populate state.ticks with last known prices + perf metrics
  → WS clients receive snapshot immediately on connect
  → Change values reflect last trading day vs day before (not +0.00)
```

#### Close-of-day (Dagster)
```
Scheduled: 20:30 NYC, weekdays
  → Query PG for all unique tickers
  → Fetch reference closes from Massive REST API
  → Write to Redis: ticker:prev_close:{T}, ticker:perf:{T}
  → Next session, ws-relay uses these for enrichment
```

### Redis keys

| Key pattern | Type | Purpose |
|---|---|---|
| `ticker:assignments` | hash | ticker → ingest node ID |
| `ticker:prev_close:{T}` | string | Previous trading day close |
| `ticker:perf:{T}` | hash | Reference closes: 5d, 1m, 3m, 6m, 1y, ytd, 3y |
| `ticker:prices:{T}` | hash | Latest price, change, changePct, volume, timestamp |
| `control:node_count` | string | Current number of ingest nodes |
| `control:assignments` | pub/sub | Assignment change notifications |

## Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (for local dev / seed scripts)

## Setup

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: set MASSIVE_API_KEY, JWT_SECRET, BETA_KEY

# 2. Start all services
docker compose up --build

# 3. Seed Redis with reference closes (first time / off-hours)
uv run python -m server.seed_redis
```

The API is available at `http://localhost:8080`. The UI is deployed to `finpipe.app` via Cloudflare Workers.

## Environment Variables

| Variable | Description |
|---|---|
| `MASSIVE_API_KEY` | API key for the Massive WebSocket + REST API |
| `POSTGRES_PASSWORD` | Password for the PostgreSQL database |
| `DATABASE_URL` | Full PostgreSQL connection string |
| `JWT_SECRET` | Secret key for signing JWT tokens |
| `BETA_KEY` | Required key for new user registration |
| `REDIS_URL` | Redis connection string (default: redis://localhost:6379) |
| `KAFKA_BOOTSTRAP` | Redpanda broker address (default: localhost:9092) |
| `NODE_ID` | Ingest node identifier (ingest-0, ingest-1, etc.) |

## API

### Auth

```
POST   /external/auth/register         create account (requires beta_key) → JWT
POST   /external/auth/login            login → JWT
POST   /external/api-key               generate API key (JWT required)
```

### Tickers

```
GET    /external/tickers/list          list watchlist (JWT or API key)
POST   /external/tickers/{ticker}      add ticker (JWT)
DELETE /external/tickers/{ticker}      remove ticker (JWT)
PATCH  /external/tickers               batch add/remove (JWT or API key)
PUT    /external/tickers/order         set watchlist order (JWT)
```

### Positions

```
GET    /external/positions             list positions (JWT)
POST   /external/positions             add position (JWT)
PATCH  /external/positions/{id}        update position (JWT)
DELETE /external/positions/{id}        delete position (JWT)
```

### Preferences

```
GET    /external/preferences           get UI preferences (JWT)
PUT    /external/preferences           save UI preferences (JWT)
```

### WebSocket

```
WS     /ws?token={JWT}                 stream enriched ticks
```

### Health

```
GET    /external/health                public health check
GET    /internal/health                pipeline status (localhost only)
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, asyncpg, aiokafka |
| Message broker | Redpanda (Kafka-compatible) |
| Cache / state | Redis 7 |
| Database | PostgreSQL 17 |
| Frontend | React 18, TypeScript, Vite |
| Deployment (UI) | Cloudflare Workers |
| Auth | JWT + bcrypt, rate-limited (slowapi) |
| Batch jobs | Dagster |
| Data source | Massive API (WebSocket + REST) |
| Containerization | Docker, docker-compose |

## Local Development with Cloudflare Tunnel

See [local-cloudflare-dev.txt](local-cloudflare-dev.txt) for instructions on exposing the local backend at `api.finpipe.app` via Cloudflare Tunnel.
