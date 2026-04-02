COMPOSE = docker compose -f deploy/backend/docker-compose.yml --env-file backend/.env

.PHONY: dev dev-build dev-down dev-logs dev-ps

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
