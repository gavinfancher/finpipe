#!/usr/bin/env bash
# Load secrets, then bring the stack up. Assumes the host already has docker,
# gcloud, and an authenticated gcloud session (or attached SA on a GCP VM).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

"$REPO_ROOT/deploy/host/load_secrets.sh"

set -a; source "$REPO_ROOT/deploy/host/.env"; set +a
docker compose -f deploy/compose.yml up -d --remove-orphans
