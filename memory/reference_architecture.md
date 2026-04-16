---
name: URL shortener architecture source of truth
description: Canonical architecture doc location and key tech decisions
type: reference
---

**Source of truth:** `research/05-HLA-high-level-architecture.md` (1648 lines, Uzbek, detailed).

**Key decisions locked in that doc:**
- Hybrid Go (redirect) + Python/FastAPI (admin API) + Python (analytics worker)
- PostgreSQL 17 + Redis 7.2 (×2: cache + app/streams) + ClickHouse 24+
- Redis Streams as event queue (NOT RabbitMQ/Kafka for POC)
- Nginx reverse proxy routes: `/{1-10 alnum}` → redirect service, `/api/*` → FastAPI, `/dashboard/*` → frontend
- MaxMind GeoLite2 for GeoIP (loaded in-memory in Go redirect for sub-5us lookup)
- JWT (access 15min + refresh 7d) + API keys (SHA-256 hashed)
- Alembic migrations for PG; ClickHouse init via SQL file

**Other research files:** 00-umumiy-xulosa (summary), 01-arxitektura-va-system-design, 02-biznes-logika-va-funksiyalar, 03-arxitekturaviy-qarorlar-va-tradeofflar, 04-ochiq-kodli-yechimlar.

**User override:** Admin panel uses **Angular 19** instead of Next.js mentioned in HLA.
