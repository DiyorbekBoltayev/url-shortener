# FastAPI Admin API — Production Reference (2026)

Research agent **R2**. Target: Admin/Control-Plane microservice. Hot redirect
is Go+Fiber (see `go-stack.md`); Python owns URL CRUD, users/teams, API keys,
analytics reads (ClickHouse), webhooks.

Verified against PyPI + upstream docs, 2026-04-14.

---

## 1. Pinned versions

FastAPI 0.11x is superseded by 0.13x but the brief pins `>=0.115`, so the
floor is 0.115 with a 0.136 ceiling. All other pins reflect current stable.

```toml
# pyproject.toml  (PEP 621, uv-managed)
[project]
name = "urlsh-admin"
version = "0.1.0"
requires-python = ">=3.12,<3.14"
dependencies = [
    "fastapi>=0.115,<0.136",
    "uvicorn[standard]>=0.41,<0.42",          # pulls uvloop + httptools
    "uvloop>=0.21; sys_platform != 'win32'",
    "sqlalchemy[asyncio]>=2.0.44,<2.1",
    "asyncpg>=0.30,<0.31",
    "alembic>=1.14,<1.15",
    "pydantic>=2.11,<2.14",
    "pydantic-settings>=2.7,<2.14",
    "pyjwt[crypto]>=2.9,<3",                  # see Gotcha #1
    "pwdlib[argon2,bcrypt]>=0.2,<0.3",        # replaces dead passlib
    "redis[hiredis]>=5.2,<6",                 # redis.asyncio built-in
    "clickhouse-connect>=0.8.10,<0.16",
    "httpx[http2]>=0.28,<0.29",
    "prometheus-fastapi-instrumentator>=7.1,<8",
    "structlog>=24.4,<26",
    "orjson>=3.10,<4",
    "tenacity>=9.0,<10",
]

[dependency-groups]
dev = [
    "pytest>=8.3,<9",  "pytest-asyncio>=0.24,<0.27",  "pytest-cov>=5",
    "testcontainers[postgres,redis]>=4.9,<5",
    "ruff>=0.8,<1",    "mypy>=1.13,<2",  "types-redis",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
package = true
```

Lock: `uv lock`. Install: `uv sync --frozen`.

---

## 2. Project layout

```
admin-api/
├── pyproject.toml, uv.lock, Dockerfile, alembic.ini
├── alembic/{env.py, script.py.mako, versions/}
├── app/
│   ├── main.py              # FastAPI() + lifespan + router mounts
│   ├── config.py            # Settings (pydantic-settings)
│   ├── database.py          # engine, session factory, Base
│   ├── deps.py              # get_db, current_user, scopes, api_key
│   ├── logging.py           # structlog
│   ├── models/              # SQLAlchemy ORM (user, url, api_key, team)
│   ├── schemas/             # Pydantic v2 (user, url, auth)
│   ├── routers/             # auth, urls, analytics, api_keys, health
│   ├── services/            # kgs, jwt, safebrowsing, webhooks
│   ├── middleware/          # ratelimit, request_id, exceptions
│   └── utils/               # base62, hashing
└── tests/ (conftest.py, test_*.py)
```

Routers stay thin (parse → service → serialise). Services own transactions.
Models never import routers.

---

## 3. Async SQLAlchemy engine + session (lifespan)

`@app.on_event("startup")` is deprecated — use `lifespan` since FastAPI 0.95.

```python
# app/database.py
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
    async_sessionmaker, create_async_engine)
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

class Base(DeclarativeBase): pass

def make_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(), echo=settings.sql_echo,
        pool_size=20, max_overflow=10,
        pool_pre_ping=True, pool_recycle=1800)

SessionLocal: async_sessionmaker[AsyncSession] | None = None
engine: AsyncEngine | None = None

async def get_session() -> AsyncIterator[AsyncSession]:
    assert SessionLocal is not None
    async with SessionLocal() as s:
        try:
            yield s; await s.commit()
        except Exception:
            await s.rollback(); raise
```

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import redis.asyncio as aioredis, clickhouse_connect
from app import database
from app.config import settings
from app.logging import configure_logging
from app.middleware.exceptions import install_exception_handlers
from app.middleware.ratelimit import RateLimitMiddleware
from app.routers import auth, urls, analytics, api_keys, health

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    database.engine = database.make_engine()
    database.SessionLocal = database.async_sessionmaker(database.engine, expire_on_commit=False)
    app.state.redis = aioredis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
    app.state.ch = await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host, port=settings.clickhouse_port,
        username=settings.clickhouse_user, database="analytics",
        password=settings.clickhouse_password.get_secret_value())
    try: yield
    finally:
        await app.state.ch.close()
        await app.state.redis.aclose()
        await database.engine.dispose()

app = FastAPI(title="URL Shortener Admin", version="0.1.0",
              default_response_class=ORJSONResponse, lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
install_exception_handlers(app)
app.add_middleware(RateLimitMiddleware, default_per_min=settings.rl_default_per_min)
app.include_router(health.router)
app.include_router(auth.router,     prefix="/api/v1/auth",      tags=["auth"])
app.include_router(urls.router,     prefix="/api/v1/urls",      tags=["urls"])
app.include_router(api_keys.router, prefix="/api/v1/api-keys",  tags=["keys"])
app.include_router(analytics.router,prefix="/api/v1/analytics", tags=["analytics"])
```

---

## 4. Pydantic v2 Settings

```python
# app/config.py
from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    env: str = Field(default="dev", pattern="^(dev|staging|prod)$")
    sql_echo: bool = False
    log_level: str = "INFO"
    database_url: SecretStr                                          # postgresql+asyncpg://...
    redis_url: SecretStr
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8443
    clickhouse_user: str = "default"
    clickhouse_password: SecretStr
    jwt_secret: SecretStr
    jwt_alg: str = "HS256"
    access_ttl_seconds: int = 15 * 60
    refresh_ttl_seconds: int = 7 * 24 * 3600
    safe_browsing_key: SecretStr
    webhook_signing_key: SecretStr
    rl_default_per_min: int = 120

@lru_cache
def _settings() -> Settings: return Settings()  # type: ignore[call-arg]
settings = _settings()
```

Call `.get_secret_value()` **only at the edge** (engine creation, JWT signing,
outbound auth header). `str(secret)` returns `"**********"`.

---

## 5. Alembic async env.py

Init: `alembic init -t async alembic`.

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.config import settings
from app.database import Base
from app.models import user, url, api_key, team  # noqa: F401 - populate metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.get_secret_value())
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    context.configure(url=settings.database_url.get_secret_value(),
                      target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
```

Key: `NullPool`, `run_sync(do_run_migrations)` bridge, models imported before `Base.metadata` is read.

---

## 6. JWT auth (access + refresh + scopes)

Access 15 min HS256. Refresh 7 d, `jti` whitelisted in Redis for single-use
revocation. Scopes via FastAPI `SecurityScopes`.

```python
# app/services/jwt.py
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt  # PyJWT
from app.config import settings

def _now(): return datetime.now(timezone.utc)
def _sign(p): return jwt.encode(p, settings.jwt_secret.get_secret_value(), settings.jwt_alg)
def issue_access(sub: str, scopes: list[str]) -> tuple[str, str]:
    jti = str(uuid4())
    return _sign({"sub": sub, "jti": jti, "type": "access", "scopes": scopes,
        "iat": _now(), "exp": _now() + timedelta(seconds=settings.access_ttl_seconds)}), jti
def issue_refresh(sub: str) -> tuple[str, str]:
    jti = str(uuid4())
    return _sign({"sub": sub, "jti": jti, "type": "refresh", "iat": _now(),
        "exp": _now() + timedelta(seconds=settings.refresh_ttl_seconds)}), jti
def decode(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_alg],
        options={"require": ["exp","iat","sub","jti","type"]})
```

```python
# app/deps.py
from typing import Annotated
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models.user import User
from app.services import jwt as jwt_svc

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", scopes={
    "urls:read": "Read URLs", "urls:write": "Create/update URLs",
    "analytics:read": "Read analytics", "admin": "Admin"})

async def get_db(s: Annotated[AsyncSession, Depends(get_session)]) -> AsyncSession: return s
async def get_current_user(
    scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> User:
    www = f'Bearer scope="{scopes.scope_str}"' if scopes.scopes else "Bearer"
    creds = HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": www})
    try:
        p = jwt_svc.decode(token)
        if p["type"] != "access": raise creds
        if await request.app.state.redis.get(f"revoked:{p['jti']}"): raise creds
        uid, token_scopes = int(p["sub"]), p.get("scopes", [])
    except (InvalidTokenError, KeyError, ValueError):
        raise creds
    user = await db.scalar(select(User).where(User.id == uid, User.active.is_(True)))
    if not user: raise creds
    for need in scopes.scopes:
        if need not in token_scopes and "admin" not in token_scopes:
            raise HTTPException(403, "Missing scope", headers={"WWW-Authenticate": www})
    return user
```

Refresh flow (excerpt):

```python
# app/routers/auth.py
@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, request: Request, db: AsyncSession = Depends(get_db)):
    try: p = jwt_svc.decode(body.refresh_token)
    except Exception: raise HTTPException(401, "Invalid refresh token")
    if p["type"] != "refresh": raise HTTPException(401, "Wrong token type")
    r = request.app.state.redis
    if not await r.delete(f"rt:{p['sub']}:{p['jti']}"):
        raise HTTPException(401, "Refresh already used/revoked")   # single-use
    user = await db.get(User, int(p["sub"]))
    access, _ = jwt_svc.issue_access(str(user.id), user.scopes)
    new_rt, new_jti = jwt_svc.issue_refresh(str(user.id))
    await r.setex(f"rt:{user.id}:{new_jti}", settings.refresh_ttl_seconds, "1")
    return TokenPair(access_token=access, refresh_token=new_rt)
```

---

## 7. API key auth (SHA-256 + Redis cache)

Store `sha256(key)` in Postgres — never plaintext. Cache lookups in Redis
(~30s) to avoid hammering PG.

```python
# app/utils/hashing.py
import hashlib, secrets
def new_api_key() -> tuple[str, str]:
    raw = "sk_live_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()
def hash_key(raw: str) -> str: return hashlib.sha256(raw.encode()).hexdigest()
```

```python
# app/deps.py (continued)
from fastapi.security import APIKeyHeader
from app.utils.hashing import hash_key
from app.models.api_key import ApiKey

api_key_hdr = APIKeyHeader(name="X-API-Key", auto_error=False)
async def get_api_caller(request: Request,
                         raw: Annotated[str | None, Depends(api_key_hdr)],
                         db: Annotated[AsyncSession, Depends(get_db)]) -> ApiKey:
    if not raw: raise HTTPException(401, "Missing API key")
    digest = hash_key(raw); r = request.app.state.redis
    key = f"apikey:{digest}"
    cached = await r.get(key)
    if cached == "DENY": raise HTTPException(403, "Revoked key")
    if cached: return ApiKey.from_cache(cached)
    row = await db.scalar(select(ApiKey).where(
        ApiKey.digest == digest, ApiKey.active.is_(True)))
    if not row:
        await r.setex(key, 30, "DENY")
        raise HTTPException(403, "Invalid key")
    await r.setex(key, 30, row.to_cache())
    return row
```

On revoke: delete the DB row **and** `redis.delete(f"apikey:{digest}")`.

---

## 8. Rate limiter (Redis sliding window)

Single Lua script; cheaper than token-bucket for flat per-minute budgets,
tighter than fixed-window.

```python
# app/middleware/ratelimit.py
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_LUA = """
local key, now, win, limit = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - win)
local cur = redis.call('ZCARD', key)
if cur >= limit then return {0, cur} end
redis.call('ZADD', key, now, now .. ':' .. math.random())
redis.call('PEXPIRE', key, win)
return {1, cur + 1}
"""

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, default_per_min: int):
        super().__init__(app); self.limit = default_per_min; self._sha = None

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/ready", "/metrics"):
            return await call_next(request)
        r = request.app.state.redis
        if self._sha is None: self._sha = await r.script_load(_LUA)
        ident = request.headers.get("X-API-Key") or request.client.host
        key = f"rl:{ident}:{request.url.path}"
        allowed, cur = await r.evalsha(self._sha, 1, key,
            int(time.time() * 1000), 60_000, self.limit)
        if not allowed:
            return JSONResponse(429, headers={"Retry-After": "60"},
                content={"success": False, "error": {
                    "code": "RATE_LIMITED", "message": "Too many requests"}})
        resp: Response = await call_next(request)
        resp.headers["X-RateLimit-Limit"] = str(self.limit)
        resp.headers["X-RateLimit-Remaining"] = str(max(self.limit - cur, 0))
        return resp
```

---

## 9. Global exception handler

Envelope: `{ "success": false, "error": { "code", "message" } }`. Success
responses pass through; the frontend wraps them.

```python
# app/middleware/exceptions.py
import structlog
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as SHE
from sqlalchemy.exc import IntegrityError

log = structlog.get_logger()
_CODE = {400:"BAD_REQUEST", 401:"UNAUTHENTICATED", 403:"FORBIDDEN",
         404:"NOT_FOUND", 409:"CONFLICT", 429:"RATE_LIMITED"}

def _body(code, msg, **extra):
    return {"success": False, "error": {"code": code, "message": msg, **extra}}
def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SHE)
    async def http_exc(request, exc):
        return ORJSONResponse(exc.status_code,
            content=_body(_CODE.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)),
            headers=getattr(exc, "headers", None))
    @app.exception_handler(RequestValidationError)
    async def val_exc(request, exc):
        return ORJSONResponse(status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_body("VALIDATION_ERROR", "Invalid payload", details=exc.errors()))
    @app.exception_handler(IntegrityError)
    async def integ(request, exc):
        log.warning("integrity_error", err=str(exc.orig))
        return ORJSONResponse(409, content=_body("CONFLICT", "Resource conflict"))
    @app.exception_handler(Exception)
    async def catch_all(request, exc):
        log.exception("unhandled", path=request.url.path)
        return ORJSONResponse(500, content=_body("INTERNAL", "Internal server error"))
```

---

## 10. URLs CRUD + base62 KGS

KGS pre-allocates short codes to a Redis SET; falls back to `base62(counter)`.

```python
# app/utils/base62.py
_A = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
def encode(n: int) -> str:
    if n == 0: return "0"
    out = []
    while n:
        n, r = divmod(n, 62); out.append(_A[r])
    return "".join(reversed(out))
def decode(s: str) -> int:
    n = 0
    for c in s: n = n * 62 + _A.index(c)
    return n
```

```python
# app/services/kgs.py
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.base62 import encode

POOL, CTR = "kgs:pool", "kgs:counter"

async def get_short_code(r: Redis, db: AsyncSession) -> str:
    code = await r.spop(POOL)
    if code: return code
    n = await r.incr(CTR)
    if n < 238_328: n += 238_328   # pad: >= 3 chars
    return encode(n)
async def refill_pool(r: Redis, db: AsyncSession, *, batch=1000) -> int:
    rows = (await db.execute(text(
        "SELECT nextval('short_code_seq') FROM generate_series(1, :n)"),
        {"n": batch})).scalars().all()
    codes = [encode(n + 238_328) for n in rows]
    if codes: await r.sadd(POOL, *codes)
    return len(codes)
```

```python
# app/schemas/url.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

class UrlCreate(BaseModel):
    target_url: HttpUrl
    custom_alias: str | None = Field(None, min_length=3, max_length=32,
                                     pattern=r"^[A-Za-z0-9_-]+$")
    expires_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)

class UrlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; short_code: str; target_url: HttpUrl
    created_at: datetime; expires_at: datetime | None; click_count: int
```

```python
# app/routers/urls.py
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.deps import get_db, get_current_user
from app.models.url import Url
from app.models.user import User
from app.schemas.url import UrlCreate, UrlOut
from app.services import kgs
from app.services.safebrowsing import is_safe

router = APIRouter()
WScope = Security(get_current_user, scopes=["urls:write"])
RScope = Security(get_current_user, scopes=["urls:read"])

@router.post("", response_model=UrlOut, status_code=status.HTTP_201_CREATED)
async def create_url(body: UrlCreate, request: Request,
                     db: Annotated[AsyncSession, Depends(get_db)],
                     user: Annotated[User, WScope]):
    if not await is_safe(str(body.target_url)):
        raise HTTPException(400, "URL flagged by Safe Browsing")
    code = body.custom_alias or await kgs.get_short_code(request.app.state.redis, db)
    row = Url(short_code=code, target_url=str(body.target_url),
              owner_id=user.id, expires_at=body.expires_at, tags=body.tags)
    db.add(row)
    try: await db.flush()
    except IntegrityError:
        raise HTTPException(409, f"Short code '{code}' already taken")
    await db.refresh(row)
    return row

@router.get("/{short_code}", response_model=UrlOut)
async def get_url(short_code: str, db: Annotated[AsyncSession, Depends(get_db)],
                  user: Annotated[User, RScope]):
    row = await db.scalar(select(Url).where(
        Url.short_code == short_code, Url.owner_id == user.id))
    if not row: raise HTTPException(404, "URL not found")
    return row
```

`short_code` column has `UNIQUE` + index; alias races surface as `IntegrityError`
→ 409.

---

## 11. Analytics router (ClickHouse)

```python
# app/routers/analytics.py
from datetime import date, timedelta
from typing import Annotated, Literal
from fastapi import APIRouter, Query, Request, Security
from app.deps import get_current_user
from app.models.user import User

router = APIRouter()
Bucket = Literal["hour", "day"]
Scope = Security(get_current_user, scopes=["analytics:read"])

async def _q(request, sql, **params):
    return (await request.app.state.ch.query(sql, parameters=params)).result_rows
@router.get("/summary")
async def summary(request: Request, short_code: str,
                  since: date = Query(default_factory=lambda: date.today() - timedelta(days=7)),
                  user: Annotated[User, Scope] = ...):
    c, u, b, ru = (await _q(request,
        """SELECT count(), uniq(ip_hash), countIf(is_bot), uniqIf(ip_hash, not is_bot)
           FROM clicks WHERE short_code={sc:String} AND ts>={since:Date}""",
        sc=short_code, since=since))[0]
    return {"short_code": short_code, "clicks": c, "uniques": u,
            "bot_clicks": b, "real_uniques": ru}

@router.get("/timeseries")
async def timeseries(request: Request, short_code: str, since: date, until: date,
                     bucket: Bucket = "day", user: Annotated[User, Scope] = ...):
    step = "toStartOfHour(ts)" if bucket == "hour" else "toDate(ts)"
    rows = await _q(request,
        f"""SELECT {step} AS t, count() FROM clicks
            WHERE short_code={{sc:String}} AND ts BETWEEN {{a:Date}} AND {{b:Date}}
            GROUP BY t ORDER BY t""",
        sc=short_code, a=since, b=until)
    return {"buckets": [{"t": r[0].isoformat(), "c": r[1]} for r in rows]}

@router.get("/geo")
async def geo(request: Request, short_code: str, user: Annotated[User, Scope] = ...):
    rows = await _q(request, "SELECT country, count() FROM clicks "
        "WHERE short_code={sc:String} GROUP BY country ORDER BY 2 DESC LIMIT 50", sc=short_code)
    return [{"country": r[0], "clicks": r[1]} for r in rows]
@router.get("/devices")
async def devices(request: Request, short_code: str, user: Annotated[User, Scope] = ...):
    rows = await _q(request, "SELECT device, os, browser, count() FROM clicks "
        "WHERE short_code={sc:String} GROUP BY device, os, browser ORDER BY 4 DESC LIMIT 100",
        sc=short_code)
    return [{"device": r[0], "os": r[1], "browser": r[2], "clicks": r[3]} for r in rows]
@router.get("/referrers")
async def referrers(request: Request, short_code: str, user: Annotated[User, Scope] = ...):
    rows = await _q(request, "SELECT referrer_domain, count() FROM clicks "
        "WHERE short_code={sc:String} GROUP BY referrer_domain ORDER BY 2 DESC LIMIT 50",
        sc=short_code)
    return [{"referrer": r[0], "clicks": r[1]} for r in rows]
```

Always use `parameters=` — never f-string user input into SQL.

---

## 12. Dockerfile (multistage, non-root)

```dockerfile
FROM python:3.12-slim-bookworm AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" PYTHONPATH="/app"
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl tini && rm -rf /var/lib/apt/lists/* && \
    groupadd --system --gid 1000 app && \
    useradd --system --uid 1000 --gid app --create-home --home-dir /home/app app
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app      /app
WORKDIR /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--loop", "uvloop", "--http", "httptools", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
```

`--workers 1` per container; scale horizontally via the orchestrator. Avoids
fork issues with asyncpg pools and Prometheus multiproc.

---

## 13. Healthcheck

```python
# app/routers/health.py
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text
from app.database import SessionLocal
router = APIRouter()

@router.get("/health", include_in_schema=False)
async def health(request: Request, response: Response):
    checks: dict[str, str] = {}
    try:
        assert SessionLocal is not None
        async with SessionLocal() as s: await s.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e: checks["postgres"] = f"fail: {e.__class__.__name__}"
    try:
        checks["redis"] = "ok" if await request.app.state.redis.ping() else "fail"
    except Exception as e: checks["redis"] = f"fail: {e.__class__.__name__}"
    ok = all(v == "ok" for v in checks.values())
    response.status_code = status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "degraded", "checks": checks}

@router.get("/ready", include_in_schema=False)
async def ready(): return {"status": "ready"}
```

Split readiness (no deps) from liveness-plus-deps: k8s readiness must fail fast on DB outage to drain traffic; liveness should *not* kill the pod because Postgres hiccuped.

---

## 14. Testing (pytest-asyncio + testcontainers)

```python
# tests/conftest.py
import asyncio, pytest, pytest_asyncio
import redis.asyncio as aioredis
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from app import database
from app.database import Base
from app.main import app

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop(); yield loop; loop.close()

@pytest.fixture(scope="session")
def pg():
    with PostgresContainer("postgres:16-alpine").with_driver("asyncpg") as c: yield c

@pytest.fixture(scope="session")
def redis_c():
    with RedisContainer("redis:7-alpine") as c: yield c

@pytest_asyncio.fixture(scope="session")
async def engine(pg):
    eng = create_async_engine(pg.get_connection_url(), echo=False)
    async with eng.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()

@pytest_asyncio.fixture
async def client(engine, redis_c):
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = aioredis.from_url(
        f"redis://{redis_c.get_container_host_ip()}:{redis_c.get_exposed_port(6379)}",
        decode_responses=True)
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c
    await app.state.redis.aclose()
```

---

## 15. pyproject.toml tooling block

`[project]` + deps are in section 1. Add tooling:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
addopts = "-ra --strict-markers --cov=app --cov-report=term-missing"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
[tool.ruff.lint]
select = ["E","F","I","UP","B","S","C4","SIM","ASYNC","RUF"]
ignore = ["S101"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
```
---

## Gotchas

1. **`python-jose` is abandoned** (no release in ~3y, pulls `ecdsa` with open CVEs). Upstream FastAPI now recommends **PyJWT** — API is near-identical. Brief pins python-jose; this doc substitutes PyJWT. If you must keep jose, pin `==3.3.0` and audit.
2. **`passlib` is dead** — imports fail on Python 3.13 (`crypt` removed). Use **`pwdlib`** with Argon2, bcrypt for backward verification. FastAPI-Users migrated in 13.0.
3. **No Gunicorn-with-Uvicorn-workers here.** Forked workers multiply asyncpg pools, need Prometheus multiproc, run lifespan N times. One uvicorn per container; orchestrator scales replicas.
4. **`pool_pre_ping=True` is mandatory** behind PgBouncer / proxies with idle timeouts, else `InterfaceError: connection was closed` after ~5 min.
5. **Alembic autogenerate silently emits empty migrations** if models aren't imported in `env.py`. `Base.metadata` fills at import time.
6. **Don't mix `@app.on_event` and `lifespan=`** — only `lifespan` runs.
7. **`SecretStr.get_secret_value()` at the edge only.** Passing `SecretStr` to SQLAlchemy/Redis/log is silently wrong: `str(secret)` returns `"**********"` which then becomes your actual password.
8. **Pydantic v2 `HttpUrl` is not a `str`.** Cast `str(body.target_url)` before SQLAlchemy assignment or get `TypeError`.
9. **Use `clickhouse_connect.get_async_client()`** — the old `AsyncClient(sync_client)` wrapper runs sync queries on a thread pool, silently defeating the event loop.
10. **Rate-limit on forwarded headers.** Behind Nginx/Traefik everything looks like `127.0.0.1`; pass `--proxy-headers --forwarded-allow-ips "*"` so Starlette's `ProxyHeadersMiddleware` rewrites `request.client.host`.
11. **ClickHouse params use `{name:Type}`** — not `%s` / `:name`. Wrong syntax silently yields full-table scans with predicate `true`.
12. **`testcontainers.postgres` defaults to psycopg2.** Call `.with_driver("asyncpg")` or `create_async_engine` rejects the DSN.
13. **Surprise: `asyncio.Lock` is not process-safe.** A per-worker in-memory lock guarding KGS pool refill won't stop two containers from both refilling — use `SET NX EX` in Redis as the mutex.
