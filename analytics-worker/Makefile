# analytics-worker Makefile
# Requires: uv (https://docs.astral.sh/uv/) + docker + docker compose

SHELL := /bin/bash
IMAGE := urlshortener/analytics-worker:latest

.PHONY: help install lock run test lint typecheck fmt build up down logs ps clean

help:
	@echo "Targets:"
	@echo "  install    uv sync (all deps + dev)"
	@echo "  lock       Regenerate uv.lock"
	@echo "  run        Run the worker locally (needs .env + running infra)"
	@echo "  test       pytest"
	@echo "  lint       ruff check"
	@echo "  fmt        ruff format"
	@echo "  typecheck  mypy"
	@echo "  build      docker build"
	@echo "  up         docker compose up -d"
	@echo "  down       docker compose down"
	@echo "  logs       tail container logs"
	@echo "  scale N=2  scale worker to N replicas"
	@echo "  ps         docker compose ps"
	@echo "  clean      drop caches"

install:
	uv sync --all-extras

lock:
	uv lock

run:
	uv run python -m worker.main

test:
	uv run pytest -q

lint:
	uv run ruff check worker tests

fmt:
	uv run ruff format worker tests

typecheck:
	uv run mypy worker

build:
	docker build -t $(IMAGE) .

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200 analytics-worker

ps:
	docker compose ps

scale:
	@test -n "$(N)" || (echo "Usage: make scale N=2" && exit 1)
	docker compose up -d --scale analytics-worker=$(N)

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ .uv
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
