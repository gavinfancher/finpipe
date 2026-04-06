# infra — AWS Resource Provisioning

Boto3 scripts that create AWS resources for finpipe. Run once to stand up the
infrastructure, then use `deploy/` to ship application code.

## Structure

```
infra/
  config.py              shared region, VPC, subnets, boto3 clients
  ec2/
    control/             streaming control node (t3.medium, on-demand)
      iam.py             role: secrets, rds, elasticache, ssm
      sg.py              inbound SSH, outbound to RDS/Valkey/cloudflared
      instance.py        launch or find the instance
    backfill/            spot instance for historical data ingestion
      iam.py             role: s3, secrets, ssm
      sg.py              outbound HTTPS only, SSM access
      instance.py        launch c5n.4xlarge spot, called by dagster
  rds/
    sg.py                inbound 5432 from VPC
    subnet.py            db subnet group (us-east-1a + 1b)
    instance.py          finpipe-db, postgres 17, db.t4g.micro
  valkey/
    sg.py                inbound 6379 from VPC
    subnet.py            cache subnet group (us-east-1a + 1b)
    instance.py          finpipe-cache, valkey 8.0, cache.t4g.micro
```

## Usage

Each script is standalone. Run from the repo root:

```bash
# provision in dependency order:
uv run python infra/rds/sg.py
uv run python infra/rds/subnet.py
uv run python infra/rds/instance.py

uv run python infra/valkey/sg.py
uv run python infra/valkey/subnet.py
uv run python infra/valkey/instance.py

uv run python infra/ec2/control/iam.py
uv run python infra/ec2/control/sg.py
uv run python infra/ec2/control/instance.py
```

All scripts are idempotent — safe to re-run.

## Backfill instances

Unlike the other resources, backfill instances are ephemeral. They're launched
by the Dagster backfill job (`dagster/jobs/backfill.py`) and terminated after
the job completes. The IAM role and security group are provisioned once; the
instance is created and destroyed per run.
