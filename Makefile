# URL Shortener — Root Orchestration Makefile
#
# This Makefile coordinates the five independent sub-repos by chaining
# their individual docker compose files through a single shared external
# network (`url-shortener-net`). Each sub-repo remains self-contained
# (its own git remote, its own Makefile) — this file just sequences
# lifecycle operations across all of them.
#
# Usage:
#   make help        # list all targets
#   make up          # create network, start infra, then start apps
#   make down        # stop apps, then stop infra
#   make health      # curl each /health endpoint and report
#   make ps          # show every container on url-shortener-net
#
# Implementation detail: recipes MUST be tab-indented (not spaces).

SHELL := /bin/bash
.DEFAULT_GOAL := help

NETWORK := url-shortener-net
SUBNET  := 172.28.0.0/16

# Each app has its own compose file we can chain with -f for logs/ps.
COMPOSE_INFRA     := docker compose -f infrastructure/docker-compose.yml
COMPOSE_APPS_ARGS := -f infrastructure/docker-compose.yml \
                     -f redirect-service/docker-compose.yml \
                     -f api-service/docker-compose.yml \
                     -f analytics-worker/docker-compose.yml \
                     -f admin-panel/docker-compose.yml
COMPOSE_ALL := docker compose $(COMPOSE_APPS_ARGS)

# List of app sub-dirs in boot order (infra first, apps second).
APPS := redirect-service api-service analytics-worker admin-panel

.PHONY: help net \
        up up-all up-infra up-apps \
        down down-all down-apps down-infra \
        logs ps health build clean \
        status verify

## ---------------------------------------------------------------------
## Help
## ---------------------------------------------------------------------

help: ## Show this help (auto-generated from ## comments)
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
	@echo "Common flows:"
	@echo "  1) make up                   # full boot (net -> infra -> apps)"
	@echo "  2) make health               # check every service"
	@echo "  3) make logs                 # tail everything"
	@echo "  4) make down                 # teardown (apps then infra)"

## ---------------------------------------------------------------------
## Network
## ---------------------------------------------------------------------

net: ## Create url-shortener-net shared bridge network (idempotent)
	@docker network inspect $(NETWORK) >/dev/null 2>&1 || \
	  docker network create --driver bridge --subnet $(SUBNET) $(NETWORK)
	@echo "network $(NETWORK) ready ($(SUBNET))"

## ---------------------------------------------------------------------
## Bring-up
## ---------------------------------------------------------------------

up-infra: net ## Start infrastructure compose (postgres, redis, clickhouse, nginx, ...)
	$(MAKE) -C infrastructure up

up-apps: ## Start the 4 app composes in dependency order
	@for svc in $(APPS); do \
	  echo ">>> starting $$svc"; \
	  $(MAKE) -C $$svc up || exit $$?; \
	done

up: up-all ## Alias for up-all

up-all: net ## Full boot: network + infra + wait + apps
	$(MAKE) up-infra
	@echo "waiting 10s for infra healthchecks..."
	@sleep 10
	$(MAKE) up-apps
	@echo ""
	@echo "==> stack is up. Try:"
	@echo "   http://localhost            (admin panel via nginx)"
	@echo "   http://localhost/api/docs   (API swagger)"
	@echo "   http://localhost:3001       (grafana)"
	@echo "   http://localhost:9090       (prometheus)"

## ---------------------------------------------------------------------
## Tear-down
## ---------------------------------------------------------------------

down-apps: ## Stop the 4 app composes (reverse order)
	@for svc in admin-panel analytics-worker api-service redirect-service; do \
	  echo ">>> stopping $$svc"; \
	  $(MAKE) -C $$svc down || true; \
	done

down-infra: ## Stop infrastructure compose
	$(MAKE) -C infrastructure down

down: down-all ## Alias for down-all

down-all: down-apps down-infra ## Stop apps then infra (network is kept)
	@echo "stack stopped. Network $(NETWORK) and volumes are preserved."

## ---------------------------------------------------------------------
## Observability
## ---------------------------------------------------------------------

logs: ## Tail logs from all 9 services across all composes
	$(COMPOSE_ALL) logs -f --tail=100

ps: ## List every container attached to url-shortener-net
	@docker ps --filter network=$(NETWORK) \
	  --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

status: ps ## Alias for ps

health: ## Curl each /health endpoint and report
	@echo "=== nginx (public entrypoint) ==="
	@curl -fsS http://localhost/healthz   && echo " OK"   || echo " FAIL"
	@echo "=== api-service /api/health ==="
	@curl -fsS http://localhost/api/health && echo " OK"  || echo " FAIL"
	@echo "=== redirect-service (via docker) ==="
	@docker exec redirect-service /app/redirect healthcheck 2>/dev/null && echo "OK" || echo "FAIL"
	@echo "=== analytics-worker :9092/-/healthy ==="
	@docker exec analytics-worker wget -qO- http://127.0.0.1:9092/-/healthy 2>/dev/null && echo " OK" || echo " FAIL"
	@echo "=== prometheus ==="
	@curl -fsS http://localhost:9090/-/healthy && echo " OK" || echo " FAIL"
	@echo "=== grafana ==="
	@curl -fsS http://localhost:3001/api/health && echo " OK" || echo " FAIL"
	@echo "=== clickhouse ==="
	@curl -fsS http://localhost:8123/ping && echo "" || echo "FAIL"
	@echo "=== minio ==="
	@curl -fsS http://localhost:9002/minio/health/live && echo " OK" || echo " FAIL"
	@echo "=== postgres (pg_isready) ==="
	@docker exec postgres pg_isready -U ushortener >/dev/null 2>&1 && echo "OK" || echo "FAIL"
	@echo "=== redis-cache ==="
	@docker exec redis-cache redis-cli ping 2>/dev/null || echo "FAIL"
	@echo "=== redis-app ==="
	@docker exec redis-app redis-cli -p 6380 ping 2>/dev/null || echo "FAIL"

## ---------------------------------------------------------------------
## Build / clean
## ---------------------------------------------------------------------

build: ## Build all docker images (infra pulls, apps build locally)
	$(MAKE) -C infrastructure up   # infra is pull-only; ensures images present
	@for svc in $(APPS); do \
	  echo ">>> building $$svc image"; \
	  $(MAKE) -C $$svc build || $(MAKE) -C $$svc docker-build || exit $$?; \
	done

clean: ## Prune dangling images and unused volumes (safe)
	docker image prune -f
	docker volume prune -f
	@echo "pruned dangling images + unused anonymous volumes"

## ---------------------------------------------------------------------
## Verification
## ---------------------------------------------------------------------

verify: ## Quick structural check — every compose references url-shortener-net
	@echo "--- checking url-shortener-net references ---"
	@for f in infrastructure/docker-compose.yml \
	          redirect-service/docker-compose.yml \
	          api-service/docker-compose.yml \
	          analytics-worker/docker-compose.yml \
	          admin-panel/docker-compose.yml; do \
	    grep -q 'url-shortener-net' "$$f" && echo "OK  $$f" || echo "FAIL $$f"; \
	done
