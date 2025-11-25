# Makefile for backend local development tasks
# Targets:
#   up           - build and start services via docker-compose
#   down         - stop and remove services and volumes
#   migrate      - run alembic migrations (waits for DB)
#   recreate     - recreate DB and run migrations
#   logs         - tail docker-compose logs
#   shell        - open a shell in the web container

COMPOSE_FILE=docker-compose.yml
# Prefer classic docker-compose if available, else use `docker compose`
DOCKER_COMPOSE := $(shell if command -v docker-compose >/dev/null 2>&1; then echo docker-compose; else echo "docker compose"; fi)
DB_HOST?=localhost
DB_HOST_CONTAINER?=db
DB_PORT?=5432
DB_URL?=postgresql+asyncpg://postgres:postgres@$(DB_HOST):$(DB_PORT)/ugc
# Use service name 'db' when running inside containers
DB_URL_CONTAINER?=postgresql+asyncpg://postgres:postgres@$(DB_HOST_CONTAINER):$(DB_PORT)/ugc

.PHONY: up down migrate recreate logs shell wait-db

up:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d --build

down:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down -v

wait-db:
	@echo "Waiting for DB at $(DB_HOST):$(DB_PORT) ..."
	@bash ./scripts/wait_for_db.sh $(DB_HOST) $(DB_PORT) 60

migrate: wait-db
	@echo "Running alembic migrations against $(DB_URL) inside web container"
	@echo "Building web image to ensure migrations and code are up-to-date"
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build web
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --rm --no-deps -e DATABASE_URL=$(DB_URL_CONTAINER) web bash -c "alembic upgrade head"

# fallback: run migrations on host (useful if you have alembic installed locally)
.PHONY: migrate-host
migrate-host: wait-db
	@echo "Running alembic migrations on host against $(DB_URL)"
	@DATABASE_URL=$(DB_URL) bash ./scripts/run_migrations.sh

recreate: down up migrate

logs:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f

shell:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec web /bin/bash

# Remote Sync Configuration
VM_USER=azureuser
VM_HOST=20.244.35.24
KEY_PATH=/home/h3110fr13nd/Downloads/SECURE/Credentials/ugc-net_key (1).pem
REMOTE_DIR=/home/azureuser/ugc-net-backend
REMOTE_DB_CONTAINER=db

.PHONY: sync-db
sync-db:
	@echo "Syncing database from remote ($(VM_HOST))..."
	@echo "Step 1: Dumping remote database..."
	@ssh -i "$(KEY_PATH)" -o StrictHostKeyChecking=no $(VM_USER)@$(VM_HOST) "cd $(REMOTE_DIR) && docker compose up -d $(REMOTE_DB_CONTAINER) && sleep 5 && docker compose exec -T $(REMOTE_DB_CONTAINER) pg_dump -U postgres ugc" > remote_dump.sql
	@echo "Step 2: Stopping web service to release DB locks..."
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) stop web
	@echo "Step 3: Recreating local database..."
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ugc"
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T db psql -U postgres -d postgres -c "CREATE DATABASE ugc"
	@echo "Step 4: Restoring dump to local database..."
	@cat remote_dump.sql | $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T db psql -U postgres -d ugc
	@rm remote_dump.sql
	@echo "Step 5: Restarting web service..."
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) start web
	@echo "Sync complete! Local database is now up to date with remote."
