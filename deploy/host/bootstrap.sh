#!/usr/bin/env bash
# One-shot bootstrap for a fresh host (homelab VM or GCP VM).
#
# Idempotent: re-running is a no-op once each step has been done.
#
# Assumes:
#   - Debian/Ubuntu (apt) host
#   - You can sudo
#   - For homelab: $HOME/.config/finpipe/sa-key.json already in place
#   - GCP_PROJECT_ID exported (or passed via /etc/finpipe.env)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<you>/finpipe/gcp/deploy/host/bootstrap.sh | bash
#   # or
#   sudo ./deploy/host/bootstrap.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/gavinfancher/finpipe.git}"
REPO_BRANCH="${REPO_BRANCH:-gcp}"
INSTALL_DIR="${INSTALL_DIR:-/opt/finpipe}"

step() { printf '\n=== %s ===\n' "$1"; }

step "install docker + git"
if ! command -v docker >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg git jq
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER" || true
fi

step "install gcloud (for load_secrets.sh)"
if ! command -v gcloud >/dev/null; then
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  sudo apt-get update && sudo apt-get install -y google-cloud-cli
fi

step "clone repo to $INSTALL_DIR"
if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  sudo mkdir -p "$INSTALL_DIR"
  sudo chown "$USER:$USER" "$INSTALL_DIR"
  git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" fetch origin "$REPO_BRANCH"
  git -C "$INSTALL_DIR" checkout "$REPO_BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only
fi

step "install systemd unit"
sudo cp "$INSTALL_DIR/deploy/host/finpipe.service" /etc/systemd/system/finpipe.service
sudo sed -i "s|@@INSTALL_DIR@@|$INSTALL_DIR|g; s|@@USER@@|$USER|g" /etc/systemd/system/finpipe.service
sudo systemctl daemon-reload
sudo systemctl enable finpipe.service

cat <<EOF

next steps:
  1. authenticate gcloud once (homelab only):
     gcloud auth activate-service-account --key-file=\$HOME/.config/finpipe/sa-key.json
  2. export GCP_PROJECT_ID=<your-project> and run:
     $INSTALL_DIR/deploy/secrets/load_secrets.sh
  3. start the stack:
     sudo systemctl start finpipe.service
  4. tail logs:
     sudo journalctl -u finpipe.service -f
EOF
