#!/bin/bash
set -euo pipefail
exec > /var/log/finpipe-setup.log 2>&1

echo "=== finpipe ec2 bootstrap ==="

REGION="us-east-1"

# Install AWS CLI (not pre-installed on Ubuntu)
apt-get update -y
apt-get install -y unzip
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

get_secret() {
  aws secretsmanager get-secret-value \
    --region "$REGION" \
    --secret-id "$1" \
    --query SecretString --output text
}

# Install Docker from official repo
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo ${UBUNTU_CODENAME:-$VERSION_CODENAME}) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu

# Pull secrets and build .env
echo "pulling secrets from Secrets Manager..."
DB_PASSWORD=$(get_secret finpipe/db-password)
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --region "$REGION" \
  --db-instance-identifier finpipe-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)
VALKEY_ENDPOINT=$(aws elasticache describe-replication-groups \
  --region "$REGION" \
  --replication-group-id finpipe-cache \
  --query 'ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address' --output text)

cat > /home/ubuntu/.env <<EOF
DATABASE_URL=postgresql://postgres:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/finpipe
REDIS_URL=redis://${VALKEY_ENDPOINT}:6379
JWT_SECRET=$(get_secret finpipe/jwt-secret)
BETA_KEY=$(get_secret finpipe/beta-key)
MASSIVE_API_KEY=$(get_secret finpipe/massive)
ADMIN_USER=admin
ADMIN_PASSWORD=$(get_secret finpipe/admin-password)
CLOUDFLARE_TUNNEL_TOKEN=$(get_secret finpipe/cloudflare-tunnel-token)
POSTGRES_PASSWORD=${DB_PASSWORD}
ECR_IMAGE=${ECR_REGISTRY}/finpipe-backend:latest
EOF

chown ubuntu:ubuntu /home/ubuntu/.env
chmod 600 /home/ubuntu/.env
echo "  .env created"

# Write docker-compose.yml (injected by instance.py from deploy/ec2/docker-compose.yml)
mkdir -p /home/ubuntu/finpipe
cat > /home/ubuntu/finpipe/docker-compose.yml <<'COMPOSE'
{{DOCKER_COMPOSE}}
COMPOSE

chown -R ubuntu:ubuntu /home/ubuntu/finpipe
echo "  docker-compose.yml created"

# Login to ECR and pull pre-built image
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Start all services
cd /home/ubuntu/finpipe
docker compose --env-file /home/ubuntu/.env up -d

echo "=== finpipe ec2 bootstrap complete ==="
