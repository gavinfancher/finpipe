# finpipe AWS Deployment

## Architecture

```
Internet
  │
  ▼
Cloudflare Tunnel (zero-trust, no inbound ports)
  │
  ▼
EC2 t3.small (us-east-1a) ─── "finpipe-streaming"
  ├── ws-relay         (FastAPI + WebSocket, port 8080, ECR image)
  ├── control          (FastAPI, port 8081, scales ECS ingest service)
  ├── redpanda         (Kafka-compatible, port 9092)
  ├── redpanda-console (admin UI, port 8888)
  └── cloudflared      (tunnel agent)
  │
  ├──► RDS PostgreSQL  (finpipe-db, port 5432)
  ├──► ElastiCache Valkey (finpipe-cache, port 6379)
  └──► ECS Fargate Spot
        └── ingest tasks (0.25 vCPU, 0.5 GB, auto-scaled by control node)

Frontend: Cloudflare Pages
```

## AWS Resources

All resources are in `us-east-1`. Provisioning scripts are in `deploy/aws/`.

| Resource | Script | Name |
|----------|--------|------|
| RDS PostgreSQL | `deploy/aws/rds.py` | `finpipe-db` |
| ElastiCache Valkey | `deploy/aws/valkey.py` | `finpipe-cache` |
| ECR Repository | manual | `finpipe-backend` |
| ECS Cluster + Service | `deploy/aws/ecs.py` | cluster: `finpipe`, service: `ingest` |
| EC2 Instance | `deploy/aws/ec2.py` | `finpipe-streaming` |
| Secrets Manager | manual (AWS CLI) | `finpipe/*` |
| Cloudflare Tunnel | Cloudflare dashboard | `finpipe-api` → `api.finpipe.app` |

## Secrets (AWS Secrets Manager)

Individual secrets under the `finpipe/` prefix:

- `finpipe/db-password`
- `finpipe/jwt-secret`
- `finpipe/beta-key`
- `finpipe/massive`
- `finpipe/admin-password`
- `finpipe/cloudflare-tunnel-token`

## Security Groups

| SG Name | Purpose | Inbound | Outbound |
|---------|---------|---------|----------|
| `finpipe-ec2-sg` | EC2 core | 9092+8081 from ECS ingest SG | 443, 80, 5432→RDS, 6379→Valkey |
| `finpipe-ecs-ingest-sg` | ECS ingest tasks | none | all (Massive API, Redpanda, Valkey) |
| `finpipe-rds-sg` | RDS | 5432 from EC2 SG | — |
| `finpipe-valkey-sg` | Valkey | 6379 from EC2 SG | — |

No SSH — shell access via AWS SSM (`make ec2-ssh`). IMDSv2 enforced.

## Deployment

### First-time setup (in order)

```bash
# 1. Provision infrastructure
uv run python deploy/aws/rds.py
uv run python deploy/aws/valkey.py
uv run python deploy/aws/ecs.py

# 2. Create secrets (replace values)
aws secretsmanager create-secret --name finpipe/db-password --secret-string 'VALUE' --region us-east-1
aws secretsmanager create-secret --name finpipe/jwt-secret --secret-string 'VALUE' --region us-east-1
aws secretsmanager create-secret --name finpipe/beta-key --secret-string 'VALUE' --region us-east-1
aws secretsmanager create-secret --name finpipe/massive --secret-string 'VALUE' --region us-east-1
aws secretsmanager create-secret --name finpipe/admin-password --secret-string 'VALUE' --region us-east-1
aws secretsmanager create-secret --name finpipe/cloudflare-tunnel-token --secret-string 'VALUE' --region us-east-1

# 3. Create ECR repo + push image (must be linux/amd64)
aws ecr create-repository --repository-name finpipe-backend --region us-east-1
make ecs-deploy

# 4. Launch EC2
uv run python deploy/aws/ec2.py

# 5. Update ECS task definition with real EC2 private IP + Valkey endpoint
```

### Pushing code updates

```bash
make ecs-deploy   # builds amd64 image, pushes to ECR, forces ECS redeployment
```

On the EC2 instance (via `make ec2-ssh`):

```bash
cd /home/ubuntu/finpipe
docker compose --env-file /home/ubuntu/.env pull
docker compose --env-file /home/ubuntu/.env up -d
```

### Make targets

```bash
# Local dev
make dev          # start local stack
make dev-build    # rebuild + start
make dev-down     # stop local stack

# EC2
make ec2-status   # instance state + IP
make ec2-ssh      # SSM shell into EC2
make ec2-logs     # tail bootstrap log
make ec2-stop     # stop instance
make ec2-start    # start instance

# ECS
make ecs-status   # ingest service state
make ecs-logs     # tail ingest CloudWatch logs
make ecs-deploy   # build + push + redeploy

# RDS
make rds-status   # endpoint + state
make rds-stop     # stop (auto-restarts in 7 days)
make rds-start    # start
```

## EC2 Bootstrap

The EC2 instance bootstraps on first boot via `deploy/ec2/user-data.sh`:

1. Installs AWS CLI + Docker
2. Pulls secrets from Secrets Manager → writes `.env`
3. Writes `docker-compose.yml` inline (no git clone)
4. Logs into ECR, pulls images, starts all containers

Bootstrap log: `/var/log/finpipe-setup.log`

## Streaming Architecture

- **control node** (EC2): polls market calendar via `pandas_market_calendars`, assigns tickers to ingest nodes via Redis, scales ECS service based on market hours
- **ingest nodes** (ECS Fargate Spot): register with control node via HTTP POST `/register`, heartbeat every 10s, stream from Massive API → Redpanda
- **ws-relay** (EC2): consumes from Redpanda, enriches ticks, broadcasts to WebSocket clients

## Configuration

Deploy scripts use constants at the top of each `deploy/aws/*.py` file for AWS account ID, VPC, and subnet IDs. Update these for your own AWS account.

The `deploy/ec2/.env.example` shows required environment variables for the EC2 docker-compose stack.
