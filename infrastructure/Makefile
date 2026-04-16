# URL Shortener — Infrastructure Makefile
# Usage: `make help`

SHELL := /bin/bash
.DEFAULT_GOAL := help

NETWORK      := url-shortener-net
SUBNET       := 172.28.0.0/16
COMPOSE      := docker compose
COMPOSE_PROD := docker compose -f docker-compose.yml -f docker-compose.prod.yml

.PHONY: help net up up-prod down down-volumes logs ps psql \
        redis-cache-cli redis-app-cli clickhouse-cli ch-init health

help:
	@echo "URL Shortener infrastructure — Makefile targets:"
	@echo ""
	@echo "  make net              # url-shortener-net tarmog'ini yarat (idempotent)"
	@echo "  make up               # dev stekni ko'tar"
	@echo "  make up-prod          # prod override bilan ko'tar"
	@echo "  make down             # stekni to'xtat (volume'lar saqlanadi)"
	@echo "  make down-volumes     # stekni to'xtat + VOLUME'LARNI O'CHIR (xavfli!)"
	@echo "  make logs             # oxirgi 100 qator + tail"
	@echo "  make ps               # servislar holati"
	@echo "  make psql             # postgres shell"
	@echo "  make redis-cache-cli  # redis-cache CLI"
	@echo "  make redis-app-cli    # redis-app CLI (port 6380)"
	@echo "  make clickhouse-cli   # clickhouse-client"
	@echo "  make ch-init          # clickhouse init.sql ni qo'lda ishga tushir"
	@echo "  make health           # barcha servislar /health ni tekshir"

net:
	@docker network inspect $(NETWORK) >/dev/null 2>&1 || \
	  docker network create --driver bridge --subnet $(SUBNET) $(NETWORK)
	@echo "network $(NETWORK) ready"

up: net
	$(COMPOSE) up -d
	@echo "stack up (dev). Grafana: http://localhost:3001  Prometheus: http://localhost:9090"

up-prod: net
	$(COMPOSE_PROD) up -d
	@echo "stack up (prod override)"

down:
	$(COMPOSE) down

down-volumes:
	@read -r -p "BARCHA URL-SHORTENER VOLUMELARINI o'chiraman — davom etamizmi? [y/N] " ans; \
	  case "$$ans" in [yY]|[yY][eE][sS]) $(COMPOSE) down -v ;; *) echo "bekor qilindi"; exit 1 ;; esac

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

psql:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ushortener} -d $${POSTGRES_DB:-urlshortener}

redis-cache-cli:
	$(COMPOSE) exec redis-cache redis-cli

redis-app-cli:
	$(COMPOSE) exec redis-app redis-cli -p 6380

clickhouse-cli:
	$(COMPOSE) exec clickhouse clickhouse-client

ch-init:
	@echo "clickhouse/init.sql qo'lda qayta ishga tushirilmoqda..."
	$(COMPOSE) exec -T clickhouse clickhouse-client --multiquery < clickhouse/init.sql

health:
	@echo "=== nginx ===";        curl -fsS http://localhost/healthz || true; echo
	@echo "=== prometheus ===";   curl -fsS http://localhost:9090/-/healthy || true; echo
	@echo "=== grafana ===";      curl -fsS http://localhost:3001/api/health || true; echo
	@echo "=== minio ===";        curl -fsS http://localhost:9002/minio/health/live || true; echo
	@echo "=== clickhouse ===";   curl -fsS http://localhost:8123/ping || true; echo
	@echo "=== postgres ===";     $(COMPOSE) exec -T postgres pg_isready -U $${POSTGRES_USER:-ushortener} || true
	@echo "=== redis-cache ===";  $(COMPOSE) exec -T redis-cache redis-cli ping || true
	@echo "=== redis-app ===";    $(COMPOSE) exec -T redis-app redis-cli -p 6380 ping || true
