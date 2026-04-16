# api-service — URL Shortener Admin API

FastAPI service that owns all business logic: URL CRUD, auth (JWT),
API keys, analytics reads (ClickHouse), domains, webhooks, QR codes.

The hot **redirect** path lives in `redirect-service` (Go + Fiber) — this
service is **not** on the redirect request path.

## Stack (LOCKED)

- Python 3.12 (`slim-bookworm`)
- FastAPI `>=0.115,<0.136`
- Uvicorn 0.41 (uvloop + httptools)
- SQLAlchemy 2.0 (asyncio) + asyncpg 0.30
- Alembic 1.14 async
- Pydantic 2.11 + pydantic-settings 2.7
- PyJWT 2.9+ (with `[crypto]`)
- pwdlib (argon2 + bcrypt) — **not** passlib
- redis[hiredis] 5.2
- clickhouse-connect 0.8.10+
- structlog 24, orjson, tenacity, httpx[http2]

## Layout

```
app/
  main.py           # create_app(), lifespan, routers
  config.py         # pydantic-settings
  database.py       # async engine/session
  redis_client.py   # cache + app pools
  clickhouse_client.py
  deps.py           # get_current_user, workspace
  exceptions.py     # AppError + handlers
  models/           # SQLAlchemy ORM
  schemas/          # Pydantic v2
  routers/          # auth, urls, analytics, domains, api_keys, webhooks, qr, users, health
  services/         # auth_service, jwt_service, url_service, kgs_service, analytics_service, ...
  middleware/       # request_id, timing, rate_limiter
  utils/            # base62, url_validator, hashing

alembic/            # async env.py, versions/001_initial.py (mirrors db/init.sql)
tests/              # pytest-asyncio + httpx AsyncClient
```

## Endpoints (see HLA 2.2)

| Area        | Route                                  |
| ----------- | -------------------------------------- |
| Auth        | `POST /api/v1/auth/{register,login,refresh,logout}` |
| URLs        | `/api/v1/urls` CRUD + `/bulk`          |
| Analytics   | `/api/v1/analytics/{code}/{summary,timeseries,geo,devices,referrers}` + `/dashboard` |
| Domains     | `/api/v1/domains` + `/{id}/verify`     |
| API keys    | `/api/v1/api-keys`                     |
| Webhooks    | `/api/v1/webhooks`                     |
| QR          | `/api/v1/urls/{id}/qr?fmt=png|svg`     |
| Users       | `/api/v1/users/me`, `/me/urls`         |
| Ops         | `/health`, `/ready`, `/metrics`        |

Success/error envelope follows INTEGRATION_CONTRACT section 7.

## Environment

Copy `.env.example` -> `.env`. Required vars:

| Var                   | Purpose                                    |
| --------------------- | ------------------------------------------ |
| `DATABASE_URL`        | `postgresql+asyncpg://...`                 |
| `REDIS_CACHE_URL`     | URL cache (db 0 on redis-cache)            |
| `REDIS_APP_URL`       | Rate limits, JWT denylist (redis-app)      |
| `CLICKHOUSE_URL`      | Analytics read endpoint                    |
| `JWT_SECRET`          | >= 32 random bytes                         |
| `CORS_ORIGINS`        | Comma-separated list                       |
| `SAFE_BROWSING_API_KEY` | optional                                 |

## Run locally (uv)

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Run in Docker

```bash
# Create the shared network once (infrastructure repo normally does this):
docker network create --driver bridge --subnet 172.28.0.0/16 url-shortener-net

docker compose up -d --build
docker compose logs -f api-service
```

Healthcheck: `curl -s localhost:8000/health` (via nginx in production).

## Tests

```bash
uv run pytest -ra
```

The default suite uses aiosqlite for speed. Tests that require Postgres
array/UUID semantics `xfail` gracefully on sqlite. For full-fidelity CI,
spin up testcontainers:

```bash
uv run pytest -m pg -ra   # (when tests are tagged)
```

## Migrations

```bash
uv run alembic revision --autogenerate -m "add <feature>"
uv run alembic upgrade head
uv run alembic downgrade -1
```

`alembic/versions/001_initial.py` mirrors `infrastructure/db/init.sql`.
In the docker-compose stack the SQL init fires on first Postgres start;
Alembic is idempotent when re-run.

## Security highlights (HLA 8)

- Passwords: argon2 (pwdlib), bcrypt fallback.
- JWT: HS256 access (15 min) + refresh (7 d), refresh is single-use (Redis consume).
- API keys: `sha256(raw)` stored; only the key prefix is shown after creation.
- URL validation: scheme whitelist (`http`, `https`), length <= 10 000, CRLF-safe.
- Rate limiting: Redis sliding window (per IP / per API key, per endpoint).
- Safe Browsing lookups: optional, guarded by `SAFE_BROWSING_API_KEY`.

## License

MIT — see `LICENSE`.
