---
title: splitting streaming into three services
date: 2026-03-29
summary: ingestion, api, and ui as independent services. why separation matters for a real-time system.
---

the streaming platform runs three independent services: ingestion (connects to massive websocket, normalizes ticks), api (enriches data, manages auth, broadcasts to clients), and ui (react spa).

why not one monolith? the ingestion service maintains a single persistent websocket connection to the data provider. if the api crashes or needs a deploy, the websocket connection stays alive — no missed ticks, no reconnection delay.

the api service handles the fan-out: one inbound tick gets enriched with historical reference prices (fetched once per ticker per session, not per tick) and broadcast to all connected ui clients. this is cpu-light work — the bottleneck is the number of websocket connections, not compute.

keeping the ui as a separate vite dev server (and eventually a static cloudflare pages deploy) means the frontend is completely decoupled. it connects to the api via websocket and rest, knows nothing about the data source.

each service can scale independently. need more api capacity? add instances behind a load balancer. the ingestion service stays as a single instance — you only need one connection to the upstream feed.
