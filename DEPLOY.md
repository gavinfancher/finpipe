# Deployment Strategy

finpipe runs on two environments with instant switchover via Cloudflare Tunnel.

```
Day-to-day:   homelab (PVE) → cloudflare tunnel → api.finpipe.app
Interviews:   EC2 (t3.large) → cloudflare tunnel → api.finpipe.app
```

Same docker-compose, same .env, same domain. The switch is a DNS route change that propagates in seconds.

## Architecture

```
                    ┌──────────────┐
                    │ finpipe.app  │  (Cloudflare Workers - static UI)
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  Cloudflare  │
                    │   Tunnel     │  ← CNAME points to one of two tunnels
                    └──┬───────┬───┘
                       │       │
          ┌────────────┘       └────────────┐
          ▼                                 ▼
   ┌──────────────┐                 ┌──────────────┐
   │   Homelab    │                 │  EC2 (spot)  │
   │  PVE VM      │                 │  t3.large    │
   │  8c / 16GB   │                 │  2c / 8GB    │
   │              │                 │              │
   │  docker      │                 │  docker      │
   │  compose     │                 │  compose     │
   │  (all svcs)  │                 │  (all svcs)  │
   └──────────────┘                 └──────────────┘
```

## One-time setup

### 1. Create two tunnels

```bash
# On homelab
cloudflared tunnel create finpipe-home

# On EC2
cloudflared tunnel create finpipe-ec2
```

### 2. Install cloudflared as a service on both machines

```bash
# Homelab
sudo cloudflared service install
# Config: ~/.cloudflared/config.yml

# EC2
# Pull tunnel credentials from Secrets Manager on boot (see EC2 setup below)
sudo cloudflared service install
```

### 3. cloudflared config (same on both machines)

```yaml
# ~/.cloudflared/config.yml
tunnel: <tunnel-id>
credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: api.finpipe.app
    service: http://localhost:8080
  - hostname: dagster.finpipe.app
    service: http://localhost:3000
  - service: http_status:404
```

### 4. Initial DNS route

```bash
cloudflared tunnel route dns finpipe-home api.finpipe.app
```

## Data layer

Postgres and Redis run on the homelab permanently. EC2 connects back to them over Tailscale (free private mesh VPN). No data sync, no managed services, no extra cost.

```
Homelab (100.x.x.1)  ◄──── Tailscale ────►  EC2 (100.x.x.2)
  Postgres :5432                               ws-relay
  Redis    :6379                               ingest nodes
  Dagster                                      control node
                                               Redpanda
```

### Why this works

- The streaming path (ticks) never hits Postgres — it's Redis + Redpanda only
- PG queries from EC2 are just auth + ticker CRUD — infrequent, 30-50ms is fine
- Redis reads for tick enrichment add ~30ms — unnoticeable on a dashboard
- Dagster always runs on homelab, connects to local PG + Redis with zero latency
- One source of truth for all data, no sync issues

### Tailscale setup (one-time)

```bash
# Homelab
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# EC2 (add to user data)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=<tailscale-auth-key>
```

Free for up to 100 devices on the personal plan.

### EC2 docker-compose override

When running on EC2, override the service URLs to point at the homelab's Tailscale IP:

```bash
# .env on EC2
DATABASE_URL=postgresql://postgres:<password>@100.x.x.1:5432/finpipe
REDIS_URL=redis://100.x.x.1:6379
```

Redpanda still runs locally on EC2 (low-latency tick ingestion matters). Only PG and Redis point home.

### What runs where

| Service | Homelab | EC2 | Notes |
|---|---|---|---|
| Postgres | always | never | Single source of truth |
| Redis | always | never | Cache + assignments + perf data |
| Dagster | always | never | Batch jobs, close-of-day |
| Redpanda | when home | when EC2 | Runs local to ingest nodes |
| Redpanda Console | when home | when EC2 | Alongside Redpanda |
| Control node | when home | when EC2 | Needs Redis (via Tailscale on EC2) |
| Ingest nodes | when home | when EC2 | Needs Redpanda (local) + Redis |
| ws-relay | when home | when EC2 | Needs everything |

## Switching environments

### Quick switch (one command)

```bash
# Switch to EC2 (for interviews / demos)
./switch-backend.sh ec2

# Switch back to homelab (day-to-day)
./switch-backend.sh home
```

### switch-backend.sh

```bash
#!/bin/bash
set -e

TARGET=${1:-home}

case $TARGET in
  ec2)
    TUNNEL=finpipe-ec2
    # Ensure services are running on EC2
    ssh finpipe-ec2 "cd ~/finpipe/stream && docker compose up -d"
    echo "started services on EC2"
    ;;
  home)
    TUNNEL=finpipe-home
    ;;
  *)
    echo "usage: ./switch-backend.sh [home|ec2]"
    exit 1
    ;;
esac

cloudflared tunnel route dns $TUNNEL api.finpipe.app
echo "api.finpipe.app → $TUNNEL"
```

## EC2 setup

### Instance

- **Type**: t3.large (2 vCPU, 8GB RAM)
- **Pricing**: spot (~$20/mo) for cost savings, on-demand (~$60/mo) for guaranteed uptime
- **Region**: us-east-1 (same as other AWS services)
- **AMI**: Ubuntu 24.04
- **Storage**: 30GB gp3 EBS (survives spot reclamation)

### User data (first boot)

```bash
#!/bin/bash
# Install docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu

# Install cloudflared
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Pull tunnel credentials from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id finpipe/cloudflared-credentials \
  --query SecretString --output text \
  > /home/ubuntu/.cloudflared/credentials.json

# Clone and start
cd /home/ubuntu
git clone https://github.com/<user>/finpipe.git
cd finpipe/stream

# Pull secrets for .env
aws secretsmanager get-secret-value \
  --secret-id finpipe/env \
  --query SecretString --output text \
  > .env

docker compose up -d
sudo cloudflared service install
```

### Secrets Manager keys

| Secret | Contents |
|---|---|
| `finpipe/cloudflared-credentials` | Tunnel credentials JSON from `cloudflared tunnel create` |
| `finpipe/env` | Full .env file contents (MASSIVE_API_KEY, JWT_SECRET, etc.) |

### IAM role

EC2 instance needs an IAM role with:
- `secretsmanager:GetSecretValue` on `finpipe/*`

## Dagster (dagster.finpipe.app)

Dagster webserver runs on the homelab and is exposed via the same Cloudflare Tunnel. Access is gated by Cloudflare Access (Zero Trust) — no auth code needed in Dagster itself.

### Start Dagster

```bash
cd ~/finpipe/dagster
uv run dagster dev -f definitions.py -h 0.0.0.0 -p 3000
```

The tunnel config already routes `dagster.finpipe.app` → `localhost:3000`.

### Cloudflare Access (auth gate)

Cloudflare Access blocks unauthorized requests at the edge before they reach your homelab.

1. Go to Cloudflare dashboard → Zero Trust → Access → Applications
2. **Add an application** → Self-hosted
   - Application name: `Dagster`
   - Domain: `dagster.finpipe.app`
3. **Add a policy**:
   - Policy name: `Admin only`
   - Action: Allow
   - Selector: Emails — `your@email.com`
4. **Auth method**: one-time PIN (email code), or connect Google/GitHub OAuth

Free for up to 50 users on the Zero Trust free plan. Anyone without access sees a Cloudflare login page — requests never reach your network.

### DNS route (one-time)

```bash
cloudflared tunnel route dns finpipe-home dagster.finpipe.app
```

Note: Dagster always runs on the homelab, even when the streaming backend is switched to EC2. The tunnel config handles both hostnames independently.

## Seeding data after switchover

After switching to a fresh environment, seed Redis with reference closes:

```bash
# SSH into the target machine
cd ~/finpipe/stream
uv run python -m server.seed_redis
```

Or if the previous environment was running recently, Redis data persists in the docker volume.

## Monitoring the switch

```bash
# Verify which tunnel is active
dig api.finpipe.app CNAME

# Health check
curl https://api.finpipe.app/external/health

# Check services
ssh finpipe-ec2 "cd ~/finpipe/stream && docker compose ps"
```

## Cost summary

| Environment | Compute | Storage | Network | Total |
|---|---|---|---|---|
| **Homelab** | Free | Free | Free (Cloudflare Tunnel) | $0/mo |
| **EC2 spot** | ~$20/mo | ~$3/mo EBS | Free (Cloudflare Tunnel) | ~$23/mo |
| **EC2 on-demand** | ~$60/mo | ~$3/mo EBS | Free (Cloudflare Tunnel) | ~$63/mo |
| **Cloudflare Workers (UI)** | Free tier | - | - | $0/mo |
