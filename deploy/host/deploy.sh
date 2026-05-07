#!/usr/bin/env bash
# Pull latest code and apply with the minimum-impact action per service.
#
# - python services (api, control, ingest, dagster-code) bind-mount the repo,
#   so a `restart` is enough; image rebuild only when uv.lock changes.
# - infra services (postgres, redis, redpanda, cloudflared) are untouched.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/finpipe}"
COMPOSE="docker compose -f deploy/compose/docker-compose.yml"

cd "$REPO_DIR"
prev="$(git rev-parse HEAD)"
git pull --ff-only
curr="$(git rev-parse HEAD)"

if [[ "$prev" == "$curr" ]]; then
  echo "no changes."
  exit 0
fi

changed="$(git diff --name-only "$prev" "$curr")"

if grep -qE '^(uv\.lock|.*pyproject\.toml)$' <<<"$changed"; then
  echo "deps changed — rebuilding images"
  $COMPOSE build api dagster-code
fi

echo "restarting code-mounted services"
$COMPOSE restart api control ingest dagster-code dagster-webserver dagster-daemon
