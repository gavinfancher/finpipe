---
title: real-time streaming
order: 3
---

live tick data flows from massive websocket feeds into an ingestion service that normalizes symbols and caches ticks. a relay service enriches each tick with historical reference prices across multiple timeframes (1d, 5d, 1m, 3m, 6m, 1y, ytd) and broadcasts enriched data to connected clients over websocket.

the streaming architecture is split into three independent services — ingestion, api, and ui — allowing each to scale independently.
