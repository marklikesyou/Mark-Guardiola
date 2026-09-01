.PHONY: install format lint typecheck check infra-up infra-down migrate api compose-up compose-down openapi

BACKEND_DIR := backend
UV := uv

install:
	cd $(BACKEND_DIR) && $(UV) sync --extra dev --extra ml

format:
	cd $(BACKEND_DIR) && $(UV) run ruff format src ../scripts
	cd $(BACKEND_DIR) && $(UV) run ruff check --fix src ../scripts

lint:
	cd $(BACKEND_DIR) && $(UV) run ruff format --check src ../scripts
	cd $(BACKEND_DIR) && $(UV) run ruff check src ../scripts

typecheck:
	cd $(BACKEND_DIR) && $(UV) run mypy

check: lint typecheck

infra-up:
	docker compose -f infra/docker-compose.yml up -d db redis

infra-down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd $(BACKEND_DIR) && $(UV) run alembic upgrade head

api:
	cd $(BACKEND_DIR) && $(UV) run uvicorn markguardiola.api.app:app --reload

compose-up:
	docker compose -f infra/docker-compose.yml up --build -d

compose-down:
	docker compose -f infra/docker-compose.yml down

openapi:
	cd $(BACKEND_DIR) && $(UV) run python ../scripts/export_openapi.py
