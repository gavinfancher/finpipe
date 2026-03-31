# Cloudflare Tunnel — Expose Local Backend at api.finpipe.app

### Prerequisites

Backend must be running on local port `8080` (e.g. `docker compose up`).

### One-Time Setup

1. **Login to Cloudflare**
   ```bash
   cloudflared tunnel login
   ```

2. **Add DNS route** — creates a CNAME for `api.finpipe.app`
   ```bash
   cloudflared tunnel route dns finpipe-api api.finpipe.app
   ```

### Run the Tunnel

```bash
cloudflared tunnel --url http://localhost:8080 run finpipe-api
```

### Update UI Build Env

**Via Cloudflare dashboard:**
Cloudflare dashboard → Workers → finpipe → Settings → Variables
Set `VITE_API_URL = https://api.finpipe.app` then redeploy.

**Or locally:**
```bash
VITE_API_URL=https://api.finpipe.app npm run build
```

### Stop

Just `Ctrl-C` the tunnel.
