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

# Install docker
curl -fsSL https://get.docker.com | sh
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

# Write docker-compose.yml directly (no git clone needed)
mkdir -p /home/ubuntu/finpipe
cat > /home/ubuntu/finpipe/docker-compose.yml <<'COMPOSE'
services:
  redpanda:
    image: redpandadata/redpanda:latest
    restart: unless-stopped
    command:
      - redpanda
      - start
      - --mode=dev-container
      - --smp=1
      - --memory=512M
      - --advertise-kafka-addr=redpanda:9092
    ports:
      - "9092:9092"
    volumes:
      - redpanda_data:/var/redpanda/data
    healthcheck:
      test: ["CMD", "rpk", "cluster", "health"]
      interval: 5s
      timeout: 3s
      retries: 5

  redpanda-console:
    image: redpandadata/console:latest
    restart: unless-stopped
    ports:
      - "8888:8080"
    environment:
      KAFKA_BROKERS: redpanda:9092
    depends_on:
      redpanda:
        condition: service_healthy

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      ws-relay:
        condition: service_started

  ws-relay:
    image: ${ECR_IMAGE:-finpipe-backend:latest}
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
      KAFKA_BOOTSTRAP: redpanda:9092
      JWT_SECRET: ${JWT_SECRET}
      BETA_KEY: ${BETA_KEY}
      MASSIVE_API_KEY: ${MASSIVE_API_KEY}
      ADMIN_USER: ${ADMIN_USER}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      SKIP_SCHEMA_INIT: "false"
    depends_on:
      redpanda:
        condition: service_healthy

  control:
    image: ${ECR_IMAGE:-finpipe-backend:latest}
    restart: unless-stopped
    command: ["uv", "run", "python", "-m", "streaming.control"]
    ports:
      - "8081:8081"
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
      CONTROL_POLL_INTERVAL: "5"
      MIN_NODES: "3"
      CONTROL_PORT: "8081"
      ECS_CLUSTER: finpipe
      ECS_SERVICE: ingest
      AWS_REGION: us-east-1
    depends_on:
      redpanda:
        condition: service_healthy

volumes:
  redpanda_data:
COMPOSE

chown -R ubuntu:ubuntu /home/ubuntu/finpipe
echo "  docker-compose.yml created"

# Login to ECR and pull pre-built image
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Start all services
cd /home/ubuntu/finpipe
docker compose --env-file /home/ubuntu/.env up -d

echo "=== finpipe ec2 bootstrap complete ==="
