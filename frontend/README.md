# frontend — React Dashboard

React/TypeScript/Vite single-page app for live market data visualization.

## Stack

- React 18 + TypeScript
- Vite
- Tailwind CSS

## Features

- Real-time tick streaming via WebSocket (`api.finpipe.app/ws`)
- Watchlist management with drag-to-reorder
- Performance metrics (5d, 1m, 3m, 6m, 1y, YTD, 3y)
- Market status indicator (pre-market, open, post-market, closed)
- JWT auth with beta key registration

## Development

```bash
npm install
npm run dev
```

Deployed to Cloudflare Pages on push to `main`.
