# Multi-Repo Docker Compose Strategy

Production reference for running 5 independent repos (`infrastructure`,
`redirect-service`, `api-service`, `analytics-worker`, `admin-panel`) as one
logical stack via a shared external Docker network.

Target: **Compose v2 plugin** (`docker compose ...`). Top-level `version:` is
obsolete in the 2026 Compose Spec — **omit it**.

---

## 0. The One Rule

All 5 repos attach every service to the **same externally-managed** bridge
network `url-shortener-net`. Every `docker-compose.yml` ends with:

```yaml
networks:
  url-shortener-net:
    external: true
    name: url-shortener-net
```

Every service body adds:

```yaml
    networks:
      - url-shortener-net
```

Inside that network, containers resolve each other by **service name**
(`postgres`, `redis-cache`, `redirect-service`, ...) via Docker's embedded
DNS at `127.0.0.11`.

---

## 1. Network bootstrap (one-time)

Create **out-of-band**. Never let compose create it implicitly — it would be
owned by whichever project `up`s first, destroyed on that project's `down`,
and name-scoped with the project prefix, which breaks cross-compose DNS.

```bash
docker network create \
  --driver bridge \
  --subnet 172.28.0.0/16 \
  --gateway 172.28.0.1 \
  url-shortener-net || true
```

Because the network is `external: true`, `docker compose down` in any repo
will **not** delete it. Destroy explicitly with `docker network rm
url-shortener-net`.

---

## 2. Env file strategy

Two-tier. Only `.env.example` files are committed; all `.env*` in
`.gitignore`.

**Shared** (`<root>/.env.shared`, symlinked into each repo) — cross-service
values that MUST match everywhere:

```dotenv
POSTGRES_USER=urlshort
POSTGRES_PASSWORD=change-me-in-prod
POSTGRES_DB=urlshort
JWT_SECRET=change-me-256-bits
CLICKHOUSE_USER=analytics
CLICKHOUSE_PASSWORD=change-me
REDIS_APP_PASSWORD=change-me
S3_ACCESS_KEY=minio-root
S3_SECRET_KEY=minio-root-change-me
GEOIP_LICENSE_KEY=xxxxxxxx
```

**Per-repo** (`<repo>/.env`) — local concerns (ports, log levels):

```dotenv
SERVICE_PORT=8080
LOG_LEVEL=info
```

Wire both in every service (shared first, so per-repo wins collisions):

```yaml
    env_file:
      - ./.env.shared
      - ./.env
```

---

## 3. `infrastructure/docker-compose.yml`

Owns every stateful + gateway service. **Only nginx publishes to the host.**
DBs are network-internal.

```yaml
name: urlshort-infra

x-logging: &logging
  driver: json-file
  options: { max-size: "10m", max-file: "3" }

x-restart: &restart { restart: unless-stopped }

services:
  postgres:
    image: postgres:17-alpine
    <<: *restart
    env_file: [./.env.shared]
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - pg-data:/var/lib/postgresql/data
      - ./init/postgres:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    logging: *logging
    networks: [url-shortener-net]

  redis-cache:                       # hot cache for redirects (port 6379)
    image: redis:7.4-alpine
    <<: *restart
    command: >
      redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
                   --save "" --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    logging: *logging
    networks: [url-shortener-net]

  redis-app:                         # durable app state (port 6380)
    image: redis:7.4-alpine
    <<: *restart
    command: >
      redis-server --port 6380 --requirepass ${REDIS_APP_PASSWORD}
                   --appendonly yes --appendfsync everysec
    volumes: [redis-app-data:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "-p", "6380", "-a", "${REDIS_APP_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    logging: *logging
    networks: [url-shortener-net]

  clickhouse:
    image: clickhouse/clickhouse-server:24.10-alpine
    <<: *restart
    env_file: [./.env.shared]
    environment:
      CLICKHOUSE_USER: ${CLICKHOUSE_USER}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
      CLICKHOUSE_DB: analytics
    ulimits:
      nofile: { soft: 262144, hard: 262144 }
    volumes:
      - clickhouse-data:/var/lib/clickhouse
      - ./init/clickhouse:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8123/ping || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    logging: *logging
    networks: [url-shortener-net]

  minio:
    image: minio/minio:latest
    <<: *restart
    command: server /data --console-address ":9001"
    env_file: [./.env.shared]
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY}
    volumes: [minio-data:/data]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:9000/minio/health/live"]
      interval: 15s
      timeout: 5s
      retries: 5
    logging: *logging
    networks: [url-shortener-net]

  geoip-updater:
    image: maxmindinc/geoipupdate:v7
    <<: *restart
    env_file: [./.env.shared]
    environment:
      GEOIPUPDATE_LICENSE_KEY: ${GEOIP_LICENSE_KEY}
      GEOIPUPDATE_EDITION_IDS: GeoLite2-City GeoLite2-ASN
      GEOIPUPDATE_FREQUENCY: 72
    volumes: [geoip-db:/usr/share/GeoIP]
    logging: *logging
    networks: [url-shortener-net]

  prometheus:
    image: prom/prometheus:v2.55.0
    <<: *restart
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=30d
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    logging: *logging
    networks: [url-shortener-net]

  grafana:
    image: grafana/grafana:11.3.0
    <<: *restart
    env_file: [./.env.shared]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    logging: *logging
    networks: [url-shortener-net]

  nginx:
    image: nginx:1.27-alpine
    <<: *restart
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    logging: *logging
    networks: [url-shortener-net]

volumes:
  pg-data: {}
  redis-app-data: {}
  clickhouse-data: {}
  minio-data: {}
  geoip-db: {}
  prometheus-data: {}
  grafana-data: {}

networks:
  url-shortener-net:
    external: true
    name: url-shortener-net
```

---

## 4. App compose — `redirect-service/docker-compose.yml`

Same shape for all 4 app repos; only name/build/env differ.

```yaml
name: urlshort-redirect

services:
  redirect-service:
    build:
      context: .
      dockerfile: Dockerfile
    image: urlshort/redirect-service:${TAG:-dev}
    restart: unless-stopped
    env_file:
      - ./.env.shared
      - ./.env
    environment:
      POSTGRES_DSN: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}?sslmode=disable
      REDIS_CACHE_URL: redis://redis-cache:6379/0
      REDIS_APP_URL:   redis://:${REDIS_APP_PASSWORD}@redis-app:6380/0
      CLICKHOUSE_URL:  clickhouse://${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}@clickhouse:9000/analytics
    # No ports: -- nginx terminates TLS and proxies over url-shortener-net.
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://127.0.0.1:8080/healthz"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 10s
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    networks: [url-shortener-net]

networks:
  url-shortener-net:
    external: true
    name: url-shortener-net
```

---

## 5. Nginx cross-compose resolution

Two must-do's:

1. **`resolver 127.0.0.11`** so nginx re-resolves on each request. Without
   it, nginx caches DNS at worker start and keeps hitting dead IPs after
   container restarts.
2. **Put the upstream hostname in a variable** — nginx only re-resolves
   hostnames referenced as variables in `proxy_pass`.

`infrastructure/nginx/nginx.conf`:

```nginx
events { worker_connections 4096; }

http {
    resolver 127.0.0.11 valid=10s ipv6=off;
    resolver_timeout 5s;

    log_format main '$remote_addr "$request" $status rt=$request_time '
                    'urt=$upstream_response_time';
    access_log /var/log/nginx/access.log main;
    sendfile on; tcp_nopush on; keepalive_timeout 65;

    server {
        listen 80 default_server;
        server_name _;

        location = /healthz { return 200 "ok\n"; }

        location /admin/ {
            set $up "admin-panel:80";
            proxy_pass http://$up;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location /api/ {
            set $up "api-service:8000";
            proxy_pass http://$up;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location / {                       # hot path: short-code redirects
            set $up "redirect-service:8080";
            proxy_pass http://$up;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }
}
```

**Do not** set `container_name:`. DNS uses the **service name**; fixing
container names causes collisions during rolling updates.

---

## 6. Healthcheck patterns

```yaml
# postgres
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s

# redis (no auth)
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 3s
  retries: 5

# redis (auth + alt port)
healthcheck:
  test: ["CMD", "redis-cli", "-p", "6380", "-a", "${REDIS_APP_PASSWORD}", "ping"]

# clickhouse
healthcheck:
  test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8123/ping || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 20s
```

`depends_on` with `condition: service_healthy` **only works inside one
compose project**. Cross-project ordering (api-service needs postgres from
infra) is enforced by the Makefile rollout (section 9).

```yaml
depends_on:
  postgres:    { condition: service_healthy }
  redis-cache: { condition: service_healthy }
```

---

## 7. Production overrides (`docker-compose.prod.yml`)

Invoked as: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.
Merge semantics: scalars overwrite, lists append, maps merge.

`infrastructure/docker-compose.prod.yml`:

```yaml
services:
  postgres:
    deploy:
      resources:
        limits:       { cpus: "2.0", memory: 4g }
        reservations: { cpus: "0.5", memory: 1g }
    mem_limit: 4g
    cpus: 2.0
    restart: always
    logging:
      driver: json-file
      options: { max-size: "50m", max-file: "5" }

  redis-cache:
    deploy:
      resources: { limits: { cpus: "1.0", memory: 768m } }
    mem_limit: 768m
    restart: always

  clickhouse:
    deploy:
      resources:
        limits:       { cpus: "4.0", memory: 8g }
        reservations: { cpus: "1.0", memory: 2g }
    mem_limit: 8g
    cpus: 4.0
    restart: always

  nginx:
    deploy:
      resources: { limits: { cpus: "1.0", memory: 256m } }
    restart: always
```

**Why both `deploy.resources` and `mem_limit`?** `deploy.resources.limits`
is the Compose-Spec canonical form; Compose v2.22+ honours it in standalone
mode, but the legacy top-level keys (`mem_limit`, `cpus`) stay as a
belt-and-braces fallback for older hosts.

Other prod overrides to apply per service:

- `restart: always` (dev uses `unless-stopped`).
- Tighter log rotation (`max-size: 50m`, `max-file: 5`).
- Drop debug ports; pin images by digest (`postgres@sha256:...`).
- `read_only: true` + `tmpfs: /tmp` for stateless services.

---

## 8. Secret management

**Recommendation for this project: env files.** All 5 services read config
from environment variables (`pgx`, `go-redis`, SQLAlchemy, Angular). Docker
Compose `secrets:` mounts as files — adopting it forces every service to
grow `_FILE`-suffixed loaders or an entrypoint shim. Not worth it for a POC.

Rules:

1. `.env.shared` and per-repo `.env` in every `.gitignore`; only
   `.env.example` is committed.
2. Shared secrets in `<root>/.env.shared`, symlinked into each repo.
3. `chmod 600 .env.shared` on the host.
4. Never paste `docker inspect` output publicly — env vars are visible.

Future migration path (Swarm secrets / Vault / SOPS) — same `secrets:`
block, different backend:

```yaml
secrets:
  postgres_password:
    external: true
services:
  postgres:
    environment: { POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password }
    secrets: [postgres_password]
```

---

## 9. Root Makefile

Layout:

```
<root>/
  .env.shared
  Makefile
  infrastructure/    redirect-service/    api-service/
  analytics-worker/  admin-panel/
```

```makefile
SHELL := /bin/bash
.ONESHELL:
.DEFAULT_GOAL := help

NETWORK := url-shortener-net
REPOS_INFRA := infrastructure
REPOS_APPS  := redirect-service api-service analytics-worker admin-panel
REPOS_ALL   := $(REPOS_INFRA) $(REPOS_APPS)

COMPOSE := docker compose
ENV_ARG := --env-file .env.shared --env-file .env

ENV ?= dev
ifeq ($(ENV),prod)
  FILES := -f docker-compose.yml -f docker-compose.prod.yml
else
  FILES := -f docker-compose.yml
endif

.PHONY: help net env up up-infra up-apps down logs ps nuke

help:
	@echo "make net | env | up | up-infra | up-apps | down"
	@echo "make logs s=<svc> | ps | nuke | ENV=prod up"

net:
	@docker network inspect $(NETWORK) >/dev/null 2>&1 || \
	  docker network create --driver bridge --subnet 172.28.0.0/16 $(NETWORK)

env:
	@for r in $(REPOS_ALL); do ln -sfn ../.env.shared $$r/.env.shared; done

up-infra: net env
	@cd infrastructure && $(COMPOSE) $(ENV_ARG) $(FILES) up -d
	@echo "waiting for infra healthchecks..."
	@for i in $$(seq 1 60); do \
	  healthy=$$(docker ps --filter "label=com.docker.compose.project=urlshort-infra" \
	            --filter "health=healthy" -q | wc -l); \
	  [ "$$healthy" -ge 5 ] && break; sleep 2; \
	done

up-apps: env
	@for r in $(REPOS_APPS); do \
	  (cd $$r && $(COMPOSE) $(ENV_ARG) $(FILES) up -d) || exit 1; \
	done

up: up-infra up-apps
	@echo "stack up (ENV=$(ENV))"

down:
	@for r in $(REPOS_APPS); do (cd $$r && $(COMPOSE) $(FILES) down) || true; done
	@cd infrastructure && $(COMPOSE) $(FILES) down

logs:
	@test -n "$(s)" || (echo "usage: make logs s=<service>"; exit 1)
	@docker logs -f --tail=200 $$(docker ps --filter "name=$(s)" -q | head -1)

ps:
	@docker ps --filter "network=$(NETWORK)" \
	  --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

nuke: down
	@docker volume ls -q | grep -E '^(urlshort|infrastructure)_' | xargs -r docker volume rm
	@docker network rm $(NETWORK) || true
```

Usage: `make net` (once), `make up`, `make ENV=prod up`, `make logs
s=redirect-service`, `make down`.

---

## 10. Rollout strategy

`depends_on` does not cross compose-project boundaries, so ordering is
enforced by the Makefile:

1. `make net` — ensure `url-shortener-net` exists (idempotent).
2. `make env` — symlink `.env.shared` into every repo.
3. Bring up `infrastructure`. Nginx boots even before app upstreams exist,
   thanks to `resolver` + variable-in-`proxy_pass`.
4. Poll infra healthchecks (Makefile `up-infra`). Wait for postgres,
   redis-cache, redis-app, clickhouse, minio to report `(healthy)`.
5. `redirect-service` up (hot path first).
6. `api-service` up.
7. `analytics-worker` up.
8. `admin-panel` up.
9. Smoke test: `curl -fsS http://localhost/healthz` (nginx),
   `curl -fsS http://localhost/api/healthz` (via nginx -> api-service).

Teardown is **reverse order**: apps down first (drains in-flight requests),
infra last. The external network persists across `down` because
`external: true`.

**Rolling a single service** (no infra restart):

```bash
cd redirect-service
docker compose pull
docker compose up -d --no-deps redirect-service
```

Nginx's `resolver valid=10s` picks up the new IP within 10s.

---

## Appendix — Gotchas

- **`version:` key is dead.** Compose Spec 2026 ignores it. Omit entirely.
- **No `container_name:`.** Breaks concurrent project usage and blue/green
  swaps. Service name is enough for DNS.
- **No `ports:` on DBs.** Only nginx publishes 80/443. Ad-hoc DB access:
  `docker compose exec postgres psql` or
  `docker run --rm --network url-shortener-net -it postgres:17 psql -h postgres -U urlshort`.
- **Set `name:` at the top of each compose file** (`urlshort-infra`,
  `urlshort-redirect`, ...) so labels/filters are predictable regardless of
  checkout directory.
- **Volumes are project-scoped.** `pg-data` declared in `infrastructure/`
  becomes `urlshort-infra_pg-data`. For cross-project volume sharing,
  declare `external: true` on the volume the same way as the network.
- **nginx `resolver valid=10s`** is a good default. Lower = DNS churn;
  higher = slow recovery after IP change.
