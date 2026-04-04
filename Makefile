RDS_HOST = finpipe-db.cv08qo42c464.us-east-1.rds.amazonaws.com
VALKEY_HOST = finpipe-cache.ujjeo1.ng.0001.use1.cache.amazonaws.com
EC2_IP = $(shell aws ec2 describe-instances \
	--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=running" \
	--query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
EC2_SSH = ssh -i ~/.ssh/macbook-pro-key ubuntu@$(EC2_IP)

LOCAL = docker compose -f deploy/local/docker-compose.yml --env-file deploy/local/.env

.PHONY: local-dev-up local-dev-down local-dev-logs \
        aws-db-up aws-db-down \
        deploy ec2-ssh ec2-status ec2-logs ec2-stop ec2-start

# --- AWS database tunnels ---

aws-db-up:
	@echo "starting SSH tunnel to RDS + Valkey..."
	@ssh -i ~/.ssh/macbook-pro-key -N -f \
		-L 5432:$(RDS_HOST):5432 \
		-L 6379:$(VALKEY_HOST):6379 \
		ubuntu@$(EC2_IP)
	@echo "tunnels up — localhost:5432 (postgres) + localhost:6379 (redis)"

aws-db-down:
	@-pkill -f "ssh.*-L 5432:$(RDS_HOST)" 2>/dev/null
	@echo "tunnels down"

# --- local dev (tunneled to AWS RDS + Valkey) ---

local-dev-up:
	@echo "starting SSH tunnel to RDS + Valkey..."
	@ssh -i ~/.ssh/macbook-pro-key -N -f \
		-L 5432:$(RDS_HOST):5432 \
		-L 6379:$(VALKEY_HOST):6379 \
		ubuntu@$(EC2_IP)
	@echo "starting backend containers..."
	$(LOCAL) up --build -d
	@echo "starting frontend..."
	@cd frontend && npm run dev &
	@echo ""
	@echo "frontend: http://localhost:5173"
	@echo "backend:  http://localhost:8080"
	@echo "redpanda: http://localhost:8888"

local-dev-down:
	$(LOCAL) down
	@echo "stopping SSH tunnel..."
	@-pkill -f "ssh.*-L 5432:$(RDS_HOST)" 2>/dev/null
	@-pkill -f "npm run dev" 2>/dev/null
	@echo "done"