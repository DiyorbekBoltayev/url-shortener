.PHONY: help install sync run dev test lint format migrate revision build up down logs clean

PYTHON ?= python
UV     ?= uv
IMAGE  ?= urlsh/api-service:0.1.0

help:
	@echo "Targets:"
	@echo "  install   -- uv sync (prod + dev)"
	@echo "  sync      -- uv sync (prod only)"
	@echo "  run       -- run uvicorn locally (.env loaded)"
	@echo "  dev       -- run uvicorn with --reload"
	@echo "  test      -- pytest"
	@echo "  lint      -- ruff check"
	@echo "  format    -- ruff format"
	@echo "  migrate   -- alembic upgrade head"
	@echo "  revision  -- alembic revision --autogenerate (pass MSG=...)"
	@echo "  build     -- docker build"
	@echo "  up        -- docker compose up -d"
	@echo "  down      -- docker compose down"
	@echo "  logs      -- docker compose logs -f api-service"
	@echo "  clean     -- remove caches"

install:
	$(UV) sync

sync:
	$(UV) sync --no-dev

run:
	$(UV) run uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	$(UV) run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	$(UV) run pytest -ra

lint:
	$(UV) run ruff check app tests

format:
	$(UV) run ruff format app tests

migrate:
	$(UV) run alembic upgrade head

revision:
	$(UV) run alembic revision --autogenerate -m "$(MSG)"

build:
	docker build -t $(IMAGE) .

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f api-service

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
