# deploy/ — finpipe runtime on GCP / homelab

Single-host docker-compose stack. Two deployment targets, one compose file:

- **homelab VM** (primary) — runs hot, authenticated to GCP via a service-account key
- **GCP VM** (planned standby) — same compose, no key file (uses the attached SA)

Bootstrap scripts that *create* the GCP project, buckets, IAM, BigLake catalog,
Dataproc, etc. live in `gcp-finpipe/` (separate repo). This directory is only
about running the app on a host that already has docker + gcloud installed and
an authenticated gcloud session.

## Layout

```
deploy/
  compose.yml                    # the only compose file
  up.sh                          # load_secrets + docker compose up -d
  load_secrets.sh                # GCP Secret Manager → deploy/.env
  env.example
  .env                           # generated, gitignored
  dockerfiles/
    python.Dockerfile            # base for api / control / ingest
    dagster.Dockerfile           # base for dagster-{code,webserver,daemon}
  dagster-config/                # bind-mounted into dagster containers
    dagster.yaml
    workspace.yaml
```

## Bring the stack up

```bash
export GCP_PROJECT_ID=<your-project>
./deploy/up.sh
```

That's it. `up.sh` regenerates `deploy/.env` from Secret Manager and runs
`docker compose up -d`.

For code changes:

```bash
git pull
docker compose -f deploy/compose.yml restart api control ingest dagster-code
```

For dep changes (`uv.lock` or any `pyproject.toml`):

```bash
docker compose -f deploy/compose.yml build api dagster-code
docker compose -f deploy/compose.yml up -d
```

## Code-mount model

Every Python service mounts the repo at `/workspace`. The image's pre-installed
venv lives at `/opt/venv` (outside the bind-mount, so it isn't shadowed) and is
on `PATH`, so commands like `uvicorn`, `python`, `dagster` work directly. Edits
to `backend/` or `dagster/` show up after a `restart` (or instantly for `api`,
which has `--reload`).

## Cloudflare tunnel

Single named tunnel, token stored as `finpipe-cloudflared-token` in Secret
Manager. Same token on homelab and GCP VM — Cloudflare treats them as
redundant connectors. Hostname → service routing is configured in the
Cloudflare dashboard, not in this repo.

## Two-host story

Homelab primary. GCP VM is brought up only for a planned demo / interview.
Procedure:

1. On homelab: `pg_dump | gzip > pgdata.sql.gz` and copy to GCP VM.
2. On GCP VM: `up.sh`, restore the dump into the `postgres` volume.
3. Stop homelab's `cloudflared` (or leave both up — Cloudflare load-balances).
