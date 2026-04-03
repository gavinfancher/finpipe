#!/bin/bash
set -euo pipefail
exec > /var/log/finpipe-setup.log 2>&1

echo "=== finpipe ec2 bootstrap ==="

# Install docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu

# Install cloudflared
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Pull cloudflared credentials from Secrets Manager
mkdir -p /home/ubuntu/.cloudflared
aws secretsmanager get-secret-value \
  --region us-east-1 \
  --secret-id finpipe/cloudflared-credentials \
  --query SecretString --output text \
  > /home/ubuntu/.cloudflared/credentials.json

# Pull cloudflared config
aws secretsmanager get-secret-value \
  --region us-east-1 \
  --secret-id finpipe/cloudflared-config \
  --query SecretString --output text \
  > /home/ubuntu/.cloudflared/config.yml

chown -R ubuntu:ubuntu /home/ubuntu/.cloudflared

# Clone repo
cd /home/ubuntu
git clone https://github.com/gavinfancher/finpipe.git
cd finpipe

# Pull .env from Secrets Manager
aws secretsmanager get-secret-value \
  --region us-east-1 \
  --secret-id finpipe/env \
  --query SecretString --output text \
  > /home/ubuntu/finpipe/.env

# Run SQL migrations against RDS
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --region us-east-1 \
  --db-instance-identifier finpipe-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)

apt-get install -y postgresql-client
source /home/ubuntu/finpipe/.env
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$RDS_ENDPOINT" -U postgres -d finpipe \
  -f /home/ubuntu/finpipe/backend/sql/001_create_schema.sql

# Start services
cd /home/ubuntu/finpipe
docker compose -f deploy/ec2/docker-compose.yml --env-file .env up -d

# Install cloudflared as systemd service
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared

echo "=== finpipe ec2 bootstrap complete ==="
