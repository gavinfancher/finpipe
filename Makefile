COMPOSE = docker compose -f deploy/compose.yaml --env-file deploy/.env

.PHONY: up down logs ps build rebuild db-info

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build

rebuild:
	$(COMPOSE) build --no-cache

# --- DataGrip / psql connection info ---
# Both postgres containers are bound to 127.0.0.1 only.
db-info:
	@set -a; . deploy/.env; set +a; \
	echo ""; \
	echo "app postgres:"; \
	echo "  host=127.0.0.1 port=5433 db=$$POSTGRES_DB user=$$POSTGRES_USER password=$$POSTGRES_PASSWORD"; \
	echo "  postgres://$$POSTGRES_USER:$$POSTGRES_PASSWORD@127.0.0.1:5433/$$POSTGRES_DB"; \
	echo ""; \
	echo "dagster postgres:"; \
	echo "  host=127.0.0.1 port=5434 db=dagster user=dagster password=$$DAGSTER_PG_PASSWORD"; \
	echo "  postgres://dagster:$$DAGSTER_PG_PASSWORD@127.0.0.1:5434/dagster"; \
	echo ""; \
	echo "valkey (redis-compatible):"; \
	echo "  host=127.0.0.1 port=6379"; \
	echo "  redis://127.0.0.1:6379/0"; \
	echo ""
