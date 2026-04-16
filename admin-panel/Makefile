# Admin panel — Makefile
# Usage: `make <target>`
.PHONY: help install dev build test test-ci lint clean \
        docker-build docker-run up down logs ps network

IMAGE      ?= urlshortener/admin-panel:latest
NETWORK    ?= url-shortener-net

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "} {printf "  %-18s %s\n", $$1, $$2}'

install: ## npm ci (fallback to npm install if no lockfile)
	npm ci --no-audit --no-fund || npm install --no-audit --no-fund

dev: ## ng serve with proxy.conf.json
	npm start

build: ## Production build (dist/admin-panel/browser)
	npm run build

test: ## Karma+Jasmine watch
	npm test

test-ci: ## Headless Chrome single-shot
	npm run test:ci

lint: ## Angular lint
	npm run lint

clean: ## Remove build artifacts
	rm -rf dist .angular node_modules/.cache

network: ## Create the shared docker network (idempotent)
	docker network inspect $(NETWORK) >/dev/null 2>&1 || \
	  docker network create --driver bridge --subnet 172.28.0.0/16 $(NETWORK)

docker-build: ## Build the production image
	docker build -t $(IMAGE) .

docker-run: docker-build ## Build + run locally on host port 8080
	docker run --rm -p 8080:80 --name admin-panel-local $(IMAGE)

up: network ## Start compose service attached to shared network
	docker compose up -d --build

down: ## Stop compose service
	docker compose down

logs: ## Tail compose logs
	docker compose logs -f --tail=200

ps: ## List compose containers
	docker compose ps
