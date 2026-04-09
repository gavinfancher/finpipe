---

## title: real-time streaming
order: 3
category: architecture
summary: three independent services — ingest, control, and relay — stream live ticks through Redpanda with sub-second latency and market-aware scheduling.

the streaming layer is the core of finpipe's real-time pipeline. it's split into three independent services that communicate through Redpanda (a Kafka-compatible message bus).

### ingest

ingest workers connect to the Massive API WebSocket feed and normalize incoming tick data. each worker registers with the control node, receives a set of assigned tickers, and pushes normalized ticks to the `market-ticks` Redpanda topic.

the Massive WebSocket allows **one connection per API key**, so production runs a **single** ingest worker; the control service caps shard count (`MAX_INGEST_NODES`, default `1`). each worker uses its container hostname as `NODE_ID` for assignments.

### control

the control node manages ticker-to-node assignments. it polls PostgreSQL for all tracked tickers (across all users' watchlists and positions), computes a round-robin assignment, and publishes updates via Redis pub/sub.

it also handles market awareness — using the NYSE calendar from `pandas_market_calendars` to detect holidays, early closes, and off-hours. outside trading sessions, ingest workers are scaled to zero.

### ws-relay

the relay service consumes enriched ticks from Redpanda and broadcasts them to connected WebSocket clients. on startup, it loads pre-computed tick data from Redis so the dashboard has data immediately, even when the market is closed.

every incoming tick is enriched with:

- **daily change** — current price vs previous session's close (n-2 trading day)
- **performance** — 5d, 1m, 3m, 6m, 1y, YTD, 3y using industry-standard calendar conventions
- all computed values are written back to Redis as a single hash per ticker (20 fields)

