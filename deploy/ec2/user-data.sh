#!/bin/bash
set -euo pipefail
exec > /var/log/finpipe-setup.log 2>&1

echo "=== finpipe ec2 bootstrap ==="

REGION="us-east-1"
REPO="https://github.com/gavinfancher/finpipe.git"

# --- Docker (official apt repo) ---

apt-get update -y
apt-get install -y ca-certificates curl unzip git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo ${UBUNTU_CODENAME:-$VERSION_CODENAME}) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu
echo "  docker installed"

# --- AWS CLI ---

curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws
echo "  aws cli installed"

# --- uv ---

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.local/bin:$PATH"
echo "  uv installed"

# --- clone repo ---

git clone --depth 1 "$REPO" /home/ubuntu/finpipe
chown -R ubuntu:ubuntu /home/ubuntu/finpipe
echo "  repo cloned"

# --- setup .env ---

cd /home/ubuntu/finpipe
uv run python deploy/ec2/setup.py
chown ubuntu:ubuntu deploy/ec2/.env
echo "  .env ready"

# --- ECR login + start services ---

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

cd /home/ubuntu/finpipe/deploy/ec2
docker compose up -d

echo "=== finpipe ec2 bootstrap complete ==="
