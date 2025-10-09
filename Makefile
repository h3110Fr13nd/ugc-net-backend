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
DB_HOST?=127.0.0.1
DB_PORT?=5432
DB_URL?=postgresql+asyncpg://postgres:postgres@$(DB_HOST):$(DB_PORT)/ugc

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
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --rm --no-deps -e DATABASE_URL=$(DB_URL) web bash -c "alembic upgrade head"

# fallback: run migrations on host (useful if you have alembic installed locally)
.PHONY: migrate-host
migrate-host: wait-db
	@echo "Running alembic migrations on host against $(DB_URL)"
	@DATABASE_URL=$(DB_URL) bash ./scripts/run_migrations.sh

recreate: down up migrate

logs:
	docker-compose -f $(COMPOSE_FILE) logs -f

shell:
	docker-compose -f $(COMPOSE_FILE) exec web /bin/bash
