# AWS Production Architecture

## Overview

Finpipe's production deployment uses a mix of AWS managed services and self-hosted
components to balance cost, operational simplicity, and scalability.

- **Managed services**: ElastiCache (Valkey) for caching/pub-sub, RDS (PostgreSQL) for
  persistent storage
- **Self-hosted**: Redpanda (Kafka-compatible streaming) on EC2
- **Auto-scaled**: Ingest workers on ECS Fargate Spot

```
┌──────────────────────────────────────────────────────┐
│  AWS Managed Services                                │
│  ┌─────────────────────┐  ┌────────────────────────┐ │
│  │ ElastiCache Valkey   │  │ RDS PostgreSQL         │ │
│  │ cache.t4g.micro      │  │ db.t4g.micro           │ │
│  │ 0.5 GiB              │  │                        │ │
│  └─────────────────────┘  └────────────────────────┘ │
└──────────────────────────────────────────────────────┘
         ▲                           ▲
         │ redis://                  │ postgresql://
         │                           │
┌────────┴───────────────────────────┴─────────────────┐
│  EC2 "Core" Node (t3.small, on-demand)               │
│  ┌──────────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │ Redpanda     │  │ Control │  │ ws-relay        │ │
│  │ 1 GB RAM     │  │         │  │ (FastAPI)       │ │
│  │ port 9092    │  │         │  │ port 8080       │ │
│  └──────────────┘  └─────────┘  └─────────────────┘ │
└──────────────────────────────────────────────────────┘
         ▲
         │ kafka:// (port 9092)
         │
┌────────┴─────────────────────────────────────────────┐
│  ECS Fargate Spot — "ingest" service                 │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐          │
│  │ ingest-0  │ │ ingest-1  │ │ ingest-2  │  ...     │
│  │ 0.25 vCPU │ │ 0.25 vCPU │ │ 0.25 vCPU │          │
│  │ 0.5GB RAM │ │ 0.5GB RAM │ │ 0.5GB RAM │          │
│  └───────────┘ └───────────┘ └───────────┘          │
│  auto-scaled by control node: 0–10 tasks             │
└──────────────────────────────────────────────────────┘
```

---

## Components

### ElastiCache Valkey (cache.t4g.micro)

Replaces self-hosted Redis. Wire-compatible — no code changes, just an endpoint swap.

- **Hot cache**: last 30 minutes of tick data
- **Pub/sub**: control ↔ ingest worker coordination
- **Memory**: 0.5 GiB (sufficient for ~1000 tickers of compact numeric data)
- **Why Valkey**: 20% cheaper than Redis OSS on ElastiCache, same protocol

### RDS PostgreSQL (db.t4g.micro)

Replaces self-hosted Postgres container. Handles backups, patching, failover.

- **Users**: control node (1 query every 5s), ws-relay (auth, CRUD)
- **Workload**: very light — <10 queries/sec at peak

### EC2 Core Node (t3.small, on-demand)

Hosts all stateful/critical services. On-demand because these must stay up during
market hours.

**Redpanda** (self-hosted, Kafka-compatible)
- Single-node, dev mode, 1 GB RAM (bump from 512M in dev compose)
- Managed Kafka (MSK) starts at ~$80-100/mo — not worth it for this throughput
- Receives ticks from ingest workers, consumed by ws-relay on localhost

**Control node**
- Polls PostgreSQL every 5s for active tickers
- Computes desired ingest node count (min 3, odd, ≤100 tickers/node)
- Publishes assignments to Valkey pub/sub
- Scales ECS ingest service via `ecs.update_service()`
- Manages market-hours awareness (weekdays, holidays)

**ws-relay** (FastAPI)
- Kafka consumer (reads from Redpanda on localhost — zero network hop)
- Enriches ticks with Redis lookups (prev close, perf data)
- Broadcasts to WebSocket clients
- REST API for auth, tickers, positions

### ECS Fargate Spot — Ingest Workers

Stateless containers that connect to the Massive API WebSocket and produce to Kafka.

- **Task size**: 0.25 vCPU / 0.5 GB RAM (I/O-bound, barely uses CPU)
- **Fargate Spot**: ~70% discount, ECS auto-replaces interrupted tasks
- **Scaling**: driven by control node, not CloudWatch metrics

Each worker:
1. Starts up, registers with control node via Redis
2. Receives ticker assignments via pub/sub
3. Opens WebSocket to Massive API, subscribes to assigned tickers
4. Normalizes ticks and produces to Kafka `market-ticks` topic

---

## Auto-Scaling Strategy

The control node is the single source of truth for scaling decisions. No separate
cron rules or CloudWatch alarms needed.

### Market hours detection

```python
import exchange_calendars as xcals
from datetime import date

nyse = xcals.get_calendar("XNYS")

def is_market_open() -> bool:
    return nyse.is_session(date.today())
```

Handles weekends, NYSE holidays, and early closes automatically.

### Scaling logic (in control/main.py)

```python
import boto3

ecs = boto3.client("ecs")

# every poll cycle (5s):
if not is_market_open():
    desired = 0
else:
    desired = node_count  # existing ticker-based calculation

current = ecs.describe_services(
    cluster="finpipe", services=["ingest"]
)["services"][0]["desiredCount"]

if current != desired:
    ecs.update_service(
        cluster="finpipe",
        service="ingest",
        desiredCount=desired,
    )
```

### Active hours

| Period                | Ingest tasks |
|-----------------------|--------------|
| Market day, pre-market → after-hours (~4 AM – 8 PM ET) | 3–10 (ticker-based) |
| Overnight             | 0            |
| Weekends              | 0            |
| NYSE holidays         | 0            |

Effective runtime: ~242 days/year × 16 hrs/day = **~3,872 hours/year** (~322 hrs/month).

---

## Networking

All components must be in the same VPC. Security group rules:

| Source            | Destination         | Port  | Protocol |
|-------------------|---------------------|-------|----------|
| EC2 Core          | ElastiCache Valkey  | 6379  | TCP      |
| EC2 Core          | RDS PostgreSQL      | 5432  | TCP      |
| ECS ingest tasks  | ElastiCache Valkey  | 6379  | TCP      |
| ECS ingest tasks  | EC2 Core (Redpanda) | 9092  | TCP      |
| Internet (users)  | EC2 Core (ws-relay) | 8080  | TCP      |
| ECS ingest tasks  | Internet (Massive API) | 443 | TCP      |

---

## Environment Variables

### EC2 Core (docker-compose)

| Service   | Variable          | Value                                              |
|-----------|-------------------|----------------------------------------------------|
| control   | `REDIS_URL`       | `redis://<valkey-endpoint>.cache.amazonaws.com:6379` |
| control   | `DATABASE_URL`    | `postgresql://<user>:<pass>@<rds-endpoint>:5432/finpipe` |
| ws-relay  | `REDIS_URL`       | same ElastiCache endpoint                          |
| ws-relay  | `DATABASE_URL`    | same RDS endpoint                                  |
| ws-relay  | `KAFKA_BOOTSTRAP` | `redpanda:9092` (localhost via docker network)     |

### ECS Ingest Tasks (task definition)

| Variable          | Value                                              |
|-------------------|----------------------------------------------------|
| `MASSIVE_API_KEY` | from Secrets Manager or SSM Parameter Store        |
| `KAFKA_BOOTSTRAP` | `<core-ec2-private-ip>:9092`                       |
| `REDIS_URL`       | `redis://<valkey-endpoint>.cache.amazonaws.com:6379` |

---

## Cost Estimate

| Component                              | Monthly cost |
|----------------------------------------|-------------|
| ElastiCache Valkey (cache.t4g.micro)   | ~$12        |
| RDS PostgreSQL (db.t4g.micro)          | ~$13        |
| EC2 Core (t3.small, on-demand, 24/7)   | ~$15        |
| ECS Fargate Spot (3 tasks × 322 hrs)   | ~$3         |
| EBS storage (20 GB)                    | ~$2         |
| **Total**                              | **~$45/mo** |

Notes:
- Prices are for us-east-1. Other regions may vary.
- EC2 Core runs 24/7 (Redpanda needs to be available for late writes/replays).
  Could be stopped overnight with additional automation if not needed.
- RDS and ElastiCache run 24/7 (always-on managed services, no stop/start for
  single-AZ micro instances on ElastiCache).
- Fargate Spot pricing assumes ~$0.0033/hr per task at 0.25 vCPU / 0.5 GB.
