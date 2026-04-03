COMPOSE = docker compose -f deploy/backend/docker-compose.yml --env-file backend/.env
EC2_COMPOSE = docker compose -f deploy/ec2/docker-compose.yml --env-file .env

.PHONY: dev dev-build dev-down dev-logs dev-ps \
        rds-status rds-migrate rds-stop rds-start \
        ec2-setup ec2-launch ec2-status ec2-ssh ec2-logs \
        switch-ec2 switch-home db-tunnel

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

ec2-setup:
	uv run python deploy/ec2/setup_aws.py

ec2-launch:
	@aws ec2 run-instances \
		--image-id $$(aws ssm get-parameters --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
			--query 'Parameters[0].Value' --output text) \
		--instance-type t3.medium \
		--iam-instance-profile Name=finpipe-ec2-profile \
		--security-group-ids $$(aws ec2 describe-security-groups --filters Name=group-name,Values=finpipe-ec2-sg \
			--query 'SecurityGroups[0].GroupId' --output text) \
		--subnet-id subnet-074afec090850ea1a \
		--user-data file://deploy/ec2/user-data.sh \
		--tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=finpipe-streaming}]' \
		--query 'Instances[0].InstanceId' --output text

ec2-status:
	@aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=finpipe-streaming" "Name=instance-state-name,Values=running,pending" \
		--query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress,LaunchTime]' \
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
		--parameters command="cat /var/log/finpipe-setup.log"

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
