COMPOSE = docker compose -f deploy/backend/docker-compose.yml --env-file backend/.env
EC2_COMPOSE = docker compose -f deploy/ec2/docker-compose.yml --env-file .env

.PHONY: dev dev-build dev-down dev-logs dev-ps \
        rds-status rds-migrate rds-stop rds-start \
        deploy ec2-deploy ec2-setup ec2-status ec2-ssh ec2-logs ec2-stop ec2-start \
        switch-ec2 switch-home db-tunnel

deploy: ec2-deploy

# --- local dev ---

dev:
	$(COMPOSE) up -d

dev-build:
	$(COMPOSE) up --build -d

dev-down:
	$(COMPOSE) down

dev-logs:
	$(COMPOSE) logs -f

dev-ps:
	$(COMPOSE) ps

# --- RDS ---

rds-status:
	@aws rds describe-db-instances --db-instance-identifier finpipe-db \
		--query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address,Endpoint.Port]' \
		--output table

rds-migrate:
	@endpoint=$$(aws rds describe-db-instances --db-instance-identifier finpipe-db \
		--query 'DBInstances[0].Endpoint.Address' --output text) && \
	source backend/.env && PGPASSWORD=$$POSTGRES_PASSWORD psql -h $$endpoint -U postgres -d finpipe -f backend/sql/001_create_schema.sql

rds-stop:
	aws rds stop-db-instance --db-instance-identifier finpipe-db --output text --query 'DBInstance.DBInstanceStatus'
	@echo "RDS stopped (auto-restarts after 7 days)"

rds-start:
	aws rds start-db-instance --db-instance-identifier finpipe-db --output text --query 'DBInstance.DBInstanceStatus'

# --- EC2 ---

EC2_HOST = ubuntu@$(shell aws ec2 describe-instances \
	--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=running" \
	--query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
EC2_SSH = ssh -i ~/.ssh/macbook-pro-key $(EC2_HOST)

ec2-deploy:
	@echo "deploying to EC2..."
	$(EC2_SSH) "cd /home/ubuntu/finpipe && git pull && cd deploy/ec2 && sudo docker compose up --build -d"
	@echo "done"

ec2-setup:
	uv run python deploy/aws/ec2/control/iam.py
	uv run python deploy/aws/ec2/control/sg.py
	uv run python deploy/aws/ec2/control/instance.py

ec2-status:
	@aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=running,pending,stopped" \
		--query 'Reservations[*].Instances[*].[InstanceId,State.Name,PrivateIpAddress,LaunchTime]' \
		--output table

ec2-ssh:
	@instance_id=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text) && \
	aws ssm start-session --target $$instance_id

ec2-logs:
	@instance_id=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text) && \
	aws ssm start-session --target $$instance_id \
		--document-name AWS-StartInteractiveCommand \
		--parameters command="tail -50 /var/log/finpipe-setup.log"

ec2-stop:
	@instance_id=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text) && \
	aws ec2 stop-instances --instance-ids $$instance_id --output text --query 'StoppingInstances[0].CurrentState.Name'

ec2-start:
	@instance_id=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=stopped" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text) && \
	aws ec2 start-instances --instance-ids $$instance_id --output text --query 'StartingInstances[0].CurrentState.Name'

# --- ECS Fargate ingest ---

ecs-setup:
	uv run python deploy/aws/ecs.py

ecs-status:
	@aws ecs describe-services --cluster finpipe --services ingest \
		--query 'services[0].[status,desiredCount,runningCount,pendingCount]' \
		--output table

ecs-logs:
	@aws logs tail /ecs/finpipe-ingest --follow

ecs-scale:
	@echo "current:" && \
	aws ecs describe-services --cluster finpipe --services ingest \
		--query 'services[0].{desired:desiredCount,running:runningCount}' --output table

ECR_REPO = $(shell aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com/finpipe-backend

ecs-deploy:
	@echo "building + pushing image..."
	docker build -t $(ECR_REPO):latest -f deploy/backend/Dockerfile .
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(ECR_REPO)
	docker push $(ECR_REPO):latest
	@echo "forcing new deployment..."
	aws ecs update-service --cluster finpipe --service ingest --force-new-deployment \
		--query 'service.deployments[0].{status:status,desired:desiredCount,running:runningCount}' --output table
	@echo "done — ECS will roll new tasks over the next few minutes"

# --- tunnel switchover ---

switch-ec2:
	cloudflared tunnel route dns finpipe-ec2 api.finpipe.app
	@echo "api.finpipe.app → finpipe-ec2"

switch-home:
	cloudflared tunnel route dns finpipe-home api.finpipe.app
	@echo "api.finpipe.app → finpipe-home"

# --- laptop → RDS via tunnel ---

db-tunnel:
	@echo "connecting localhost:5432 → RDS via cloudflare tunnel..."
	cloudflared access tcp --hostname db.finpipe.app --url localhost:5432
