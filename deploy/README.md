# deploy/ — finpipe runtime on GCP / homelab

Single-host docker-compose stack. Two deployment targets, one compose file:

- **homelab VM** (primary) — runs hot, authenticated to GCP via a service-account key
- **GCP VM** (planned standby) — same compose, no key file (uses the attached SA)

Bootstrap scripts that *create* the GCP project, buckets, IAM, BigLake catalog,
Dataproc, etc. live in `gcp-finpipe/` (separate repo). This directory is only
about running the app on a host that already has GCP access.

## Layout

```
deploy/
  compose/
    docker-compose.yml         # all services
    dagster/                   # mounted into dagster containers
      dagster.yaml
      workspace.yaml
  docker/
    Dockerfile.python          # base for api / control / ingest
    Dockerfile.dagster         # base for dagster-{code,webserver,daemon}
  secrets/
    load_secrets.sh            # GCP Secret Manager → .env
    .env.example
    .env                       # generated, gitignored
  host/
    bootstrap.sh               # one-shot host setup (docker, gcloud, clone, systemd)
    finpipe.service            # systemd unit
    deploy.sh                  # `git pull` + restart code-mounted services
```

`deploy/ec2/` and `deploy/local/` are AWS-era and will be removed once the GCP
path is live; left in place so `main` keeps working.

## First-time setup on a host

```bash
# 1. (homelab only) drop the SA key in place
mkdir -p ~/.config/finpipe && cp sa-key.json ~/.config/finpipe/

# 2. bootstrap the host (installs docker + gcloud, clones repo, installs systemd unit)
sudo ./deploy/host/bootstrap.sh

# 3. authenticate gcloud (homelab only)
gcloud auth activate-service-account --key-file=$HOME/.config/finpipe/sa-key.json

# 4. pull secrets from Secret Manager and write deploy/secrets/.env
export GCP_PROJECT_ID=<your-project>
export GCS_LAKEHOUSE_BUCKET=finpipe-lakehouse
export GCS_DATA_BUCKET=finpipe-data
./deploy/secrets/load_secrets.sh

# 5. (homelab only) tell compose where the SA key lives
echo "SA_KEY_PATH=$HOME/.config/finpipe/sa-key.json" >> deploy/secrets/.env
echo "GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa-key.json" >> deploy/secrets/.env

# 6. start
sudo systemctl start finpipe.service
```

## Day-to-day deploy

```bash
./deploy/host/deploy.sh
```

`git pull` + `docker compose restart` for code-mounted services. Rebuilds the
Python image only when `uv.lock` or any `pyproject.toml` changed.

## Code-mount model

Every Python service mounts the repo at `/workspace`. Compose entrypoints run
`uv run …` against the pre-installed `.venv` baked into the image. Edits to
`backend/` or `dagster/` show up after a `restart` (or instantly for `api`,
which has `--reload`).

When deps change:

```bash
docker compose -f deploy/compose/docker-compose.yml build api dagster-code
docker compose -f deploy/compose/docker-compose.yml up -d
```

## Cloudflare tunnel

Single named tunnel, token stored as `finpipe-cloudflared-token` in Secret
Manager. Same token on homelab and GCP VM — Cloudflare treats them as
redundant connectors. Hostname → service routing is configured in the
Cloudflare dashboard, not in this repo.

## Two-host story

Homelab primary. GCP VM is brought up only for a planned demo / interview.
Procedure:

1. On homelab: `pg_dump | gzip > pgdata.sql.gz` and copy to GCP VM.
2. On GCP VM: `bootstrap.sh`, `load_secrets.sh`, restore the dump into the
   `postgres` volume, `systemctl start finpipe.service`.
3. Stop homelab's `cloudflared` (or leave both up — Cloudflare load-balances).
