---
name: Project scope and constraints
description: URL shortener architecture, services, repo strategy, tech stack constraints
type: project
---

**Goal:** Production-ready bit.ly-like URL shortener.

**Services (each its own git repo + folder under url-shortener/):**
1. `infrastructure` — shared docker-compose (Postgres, Redis×2, ClickHouse, Nginx, Prometheus, Grafana, MinIO, GeoIP updater)
2. `redirect-service` — Go 1.22+ / Fiber v2, target <5ms p99
3. `api-service` — FastAPI 0.115+, async SQLAlchemy 2.0, Pydantic v2, asyncpg
4. `analytics-worker` — Python async, Redis Streams consumer → ClickHouse
5. `admin-panel` — **Angular 19** (NOT Next.js/React despite HLA mentioning it — user explicitly required Angular 19)

**Networking:** All services attach to single external Docker network `url-shortener-net` so infra compose + per-service composes interoperate.

**Why:** User wants each service independently deployable/pushable; infra isolated from app services; network shared for dev.

**How to apply:** Each service directory = self-contained repo (own Dockerfile, docker-compose.yml, README, .env.example, .gitignore). Never mix code across services. Reference `url-shortener-net` as external in each compose file.
