# finpipe deploy

## architecture

```
Internet
  │
  ▼
Cloudflare Tunnel (api.finpipe.app → ws-relay:8080)
  │
  ▼
EC2 t3.small (us-east-1a) ─── "finpipe-streaming"
  ├── ws-relay         (FastAPI + WebSocket, port 8080)
  ├── control          (ticker assignment, port 8081)
  ├── ingest           (Massive API → Redpanda, scalable)
  ├── redpanda         (Kafka-compatible, port 9092)
  ├── redpanda-console (admin UI, port 8888)
  └── cloudflared      (tunnel agent)
  │
  ├──► RDS PostgreSQL    (finpipe-db, db.t4g.micro)
  └──► ElastiCache Valkey (finpipe-cache, cache.t4g.micro)

Frontend: Cloudflare Pages (finpipe.app)
```

## directory layout

```
deploy/
├── aws/           # infrastructure provisioning scripts (boto3)
│   ├── config.py  # shared VPC, subnet, account constants
│   ├── ec2/       # EC2 instance + SG + IAM
│   ├── rds/       # RDS PostgreSQL
│   └── valkey/    # ElastiCache Valkey
├── docker/        # shared Dockerfile (used by ec2 + local)
├── ec2/           # EC2 docker-compose, cloudflared config, setup.py
├── local/         # local dev docker-compose + .env
└── dagster/       # dagster deployment config
```

## secrets (AWS Secrets Manager)

individual entries under `finpipe/`:

- `finpipe/db-password`
- `finpipe/jwt-secret`
- `finpipe/beta-key`
- `finpipe/massive` (Massive API secret key)
- `finpipe/admin-password`
- `finpipe/cloudflared-credentials` (tunnel credentials JSON)
- `finpipe/cloudflared-cert` (origin cert PEM)

## deploying

### push to EC2 (from laptop)

```bash
make deploy
# or just push to main — GitHub Actions runs the same thing
```

this SSHs into the EC2 instance, runs `git pull`, and rebuilds containers.

### first-time EC2 setup

the EC2 user-data script (`deploy/ec2/user-data.sh`) handles bootstrap:

1. installs docker, AWS CLI, uv
2. clones the repo
3. runs `deploy/ec2/setup.py` — pulls secrets from Secrets Manager, resolves RDS/Valkey endpoints, writes `.env` + cloudflared credentials
4. `docker compose up --build -d`

### local dev

```bash
make local-dev-up    # SSH tunnel to RDS + Valkey, backend containers, frontend
make local-dev-down  # tear it all down
```

connects to real AWS RDS + Valkey via SSH tunnel through the EC2 instance.
containers use `host.docker.internal` to reach tunneled ports on localhost.

### database access (DataGrip, redis-cli, psql)

```bash
make aws-db-up    # SSH tunnel: localhost:5432 → RDS, localhost:6379 → Valkey
make aws-db-down  # kill tunnels
```

## cloudflare tunnel

the tunnel runs as a container in the EC2 docker-compose. config:

- `deploy/ec2/cloudflared-config.yml` — ingress rules (api.finpipe.app → ws-relay:8080)
- credentials + cert are pulled from Secrets Manager by `setup.py`
- tunnel ID: `ad360029-e242-4123-888d-f156fc0bc701`
- DNS: `api.finpipe.app` CNAME → tunnel

## CI/CD

`.github/workflows/deploy.yml` — triggers on push to main (excluding frontend/dagster/markdown).

GitHub secrets needed:
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (IAM user `finpipe-github-actions`, ec2:DescribeInstances only)
- `EC2_SSH_KEY` (contents of SSH private key)

GitHub variables:
- `EC2_INSTANCE_ID` (`i-00087dd289e2900f8`)

## make targets

```bash
# local dev
make local-dev-up     # tunnel + containers + frontend
make local-dev-down   # stop everything
make local-dev-logs   # tail container logs

# database tunnels
make aws-db-up        # SSH tunnel to RDS + Valkey
make aws-db-down      # kill tunnels

# EC2
make deploy           # git pull + rebuild on EC2
make ec2-ssh          # SSH into EC2
make ec2-status       # docker ps on EC2
make ec2-logs         # docker compose logs on EC2
make ec2-stop         # stop EC2 instance
make ec2-start        # start EC2 instance
```
