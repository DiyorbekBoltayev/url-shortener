# RV8 — api-service Backend: Code Quality, Performance, Correctness

Reviewer: RV8  Date: 2026-04-14
Scope: `api-service/app/**`, `api-service/alembic/**`

Severity tags: **BLOCKER** (broken flow), **HIGH** (latency/correctness win), **MED** (architecture cleanup).

---

## 1. BLOCKERS — bugs / broken flows

### B1. `_primary_workspace_id(user)` hard-coded to `None` — workspace scoping broken
`app/routers/urls.py:23-26`

```python
def _primary_workspace_id(user: User) -> UUID | None:
    return None
```

Result: every URL created through `POST /api/v1/urls` is written with `workspace_id = NULL`. The dashboard ClickHouse query (`analytics_service.dashboard`) filters by `workspace_id`, but `urls.workspace_id` is never populated from this router, and the redirect/worker tags clicks with whatever the URL carries. Workspace dashboards will always show zeros for newly-created links. Webhook/domain routers use `get_current_workspace`; this router and `bulk_create` (line 161 passes `workspace_id=None`) do not.

**Patch**: inject `Workspace` like the other routers and pass its id through to the service.

```python
# routers/urls.py  —  replace _primary_workspace_id + create_url + bulk_create
from app.deps import get_current_workspace
from app.models.workspace import Workspace

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[URLOut],
)
async def create_url(
    body: URLCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    cache=Depends(get_cache_redis),
    user: Annotated[User, WriteScope] = ...,
):
    await is_safe(body.long_url)
    row = await url_service.create_url(
        db, cache,
        user_id=user.id,
        workspace_id=workspace.id,
        body=body,
    )
    return {"success": True, "data": URLOut.model_validate(row)}
```

Apply the same change to `bulk_create` (line 149) and `list_urls` / `my_urls` (pass `workspace_id=workspace.id`, leave `user_id=None` or scope by workspace).

Delete the dead `_primary_workspace_id` helper.

---

### B2. Session commit clobbered by `db.rollback()` inside `url_service.create_url`
`app/services/url_service.py:89-97`

```python
try:
    await db.flush()
except IntegrityError:
    await db.rollback()            # <-- rolls back the whole request
    ...
```

`get_session` (database.py:48-58) already handles rollback on exception. Calling `session.rollback()` inside the service ends the active transaction; the subsequent `db.add()` / `db.flush()` in the next loop iteration will use a *new* transaction but all pending writes from the same request (e.g. a prior `auth_service` side effect, or a second URL in `bulk_create`) are gone. In `bulk_create` this means *every previous successfully-created URL is rolled back whenever a single code collides*.

**Patch**: use a SAVEPOINT per attempt so only the failing insert is undone.

```python
# services/url_service.py
from sqlalchemy.exc import IntegrityError

for attempt in range(5):
    code = short_code or await kgs_service.next_short_code(cache_redis)
    row = Url(short_code=code, long_url=long_url, ...)
    try:
        async with db.begin_nested():   # SAVEPOINT
            db.add(row)
            await db.flush()
    except IntegrityError:
        if short_code:
            raise Conflict(f"Short code '{short_code}' is already taken") from None
        continue
    await _write_cache(cache_redis, row)
    await db.refresh(row)
    return row
```

---

### B3. `bulk_create` loses the whole batch on a single failure
`app/routers/urls.py:149-174`

After B2 is fixed, `bulk_create` still has the issue that the top-level `except Exception` swallows `IntegrityError` but the outer session is *already* in a failed state if the service ever called `rollback`. Even with B2's SAVEPOINT fix, a `BadRequest` raised by `validate_long_url` on the first item currently commits nothing (the dep layer commits on success but the exception escapes). Wrap each item in its own SAVEPOINT and explicitly flush, *or* accept that the handler writes all-or-nothing.

**Patch** (catch-all inside SAVEPOINT, then flush between items):

```python
for idx, item in enumerate(body.urls):
    try:
        async with db.begin_nested():
            row = await url_service.create_url(
                db, cache, user_id=user.id, workspace_id=workspace.id, body=item
            )
        created.append(URLOut.model_validate(row))
    except Exception as exc:  # noqa: BLE001
        errors.append({"index": idx, "error": str(exc)})
```

---

### B4. `RateLimitMiddleware` runs before exception handlers and swallows the ID
`app/main.py:74-76`

Middleware is registered in order: CORS → RequestID → Timing → RateLimit. Because Starlette/FastAPI reverses the order (last registered = innermost), RateLimit wraps everything. When it returns a bespoke 429 `JSONResponse` (line 87-95), the response skips `install_exception_handlers`, so the `X-Request-ID` header is **not** attached (good — RequestIDMiddleware still runs because it's outer, but wait: see below). It *does* skip Timing's `X-Response-Time-Ms`. Worse, the returned envelope is manually inlined and duplicates `_envelope()` — any future shape change will drift. Also the rate-limit 429 response never goes through `ORJSONResponse` — it uses the default `JSONResponse` which is ~3× slower at encoding.

**Patch**: raise `RateLimited` (already defined in `exceptions.py`) instead of returning `JSONResponse`:

```python
from app.exceptions import RateLimited

if not allowed:
    raise RateLimited("Too many requests", retry_after=60)
```

And in `app/exceptions.py` the `_app_error` handler should add the `Retry-After` header:

```python
async def _app_error(_: Request, exc: AppError) -> ORJSONResponse:
    headers = {}
    if exc.status_code == 429 and "retry_after" in exc.extra:
        headers["Retry-After"] = str(exc.extra["retry_after"])
    return ORJSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, **exc.extra),
        headers=headers or None,
    )
```

Note `BaseHTTPMiddleware.dispatch` cannot raise — it must call `call_next` and return a `Response`. So the above requires converting the rate limiter to pure ASGI middleware **or** keeping `JSONResponse` but at minimum switching to `ORJSONResponse` and fixing the middleware order (see B5).

---

### B5. Middleware order: RateLimit runs **before** RequestID context-binds
`app/main.py:74-76`

FastAPI/Starlette executes middleware last-added-first-run. Current order:

```
add_middleware(CORSMiddleware)            # outermost
add_middleware(RequestIDMiddleware)
add_middleware(TimingMiddleware)
add_middleware(RateLimitMiddleware)       # innermost → runs FIRST on request, LAST on response
```

Wait — that's wrong. `BaseHTTPMiddleware` added *last* runs closest to the app, meaning on an incoming request the order is CORS → RequestID → Timing → RateLimit → route. Good — but the rate-limit 429 `JSONResponse` doesn't get the `X-Request-ID` header attached by RequestID because the outer middleware adds it to the final response, which works here. **However**, RateLimit uses `log.info` via structlog's contextvars — these are bound by RequestID — so a 429 log line *does* carry request_id only because RequestID is outer. This is currently correct but fragile. Document the invariant.

What's actually wrong: **TimingMiddleware** (`app/middleware/timing.py:19-27`) logs `request_id` only transitively via structlog contextvars. When the rate-limit middleware short-circuits, TimingMiddleware *still* sees the response and emits `X-Response-Time-Ms` — that works. But CORS preflight `OPTIONS` requests hit RateLimit, which may 429 them before CORS can respond. Preflights should bypass rate limiting.

**Patch** in `middleware/rate_limiter.py:67`:

```python
if request.method == "OPTIONS" or request.url.path in {"/health", "/ready", "/metrics"}:
    return await call_next(request)
```

---

### B6. `AppError.extra` stomped by `None` filter — `Retry-After` lost
`app/exceptions.py:79-82`

```python
def _envelope(code, message, **extra):
    err = {"code": code, "message": message}
    err.update({k: v for k, v in extra.items() if v is not None})
```

For `RateLimited("...", retry_after=60)`, `extra={"retry_after": 60}` survives, but there's no corresponding `Retry-After` HTTP header (see B4 patch). The body carries the hint, the HTTP-compliant header does not. Fix as in B4.

---

### B7. `refill_pool` is **never called** — KGS pool stays empty forever
`app/services/kgs_service.py:44` — only consumer of `POOL_KEY`

No call from `app/main.py` lifespan, no call from any router, no cron. Result: `next_short_code` always falls through to `random_short_code(7)`. That's harmless functionally (birthday collisions are rare) but the "pool" sell is a lie; every request burns a `SPOP` RTT against empty-key Redis. Also custom-slug collision retry always requests a "new auto code", which means if the user passes `custom_slug`, the `for attempt in range(5)` loop never actually runs for custom slugs — good — but the code comment suggests pool use.

**Patch** — fire an async refill on startup and schedule periodic top-ups:

```python
# app/main.py  (inside lifespan, after init_redis())
import asyncio
from app.services import kgs_service

async def _refill_loop():
    while True:
        try:
            r = redis_client.get_app_redis()
            count = await r.scard(kgs_service.POOL_KEY)
            if count < 250:
                await kgs_service.refill_pool(r, batch=500)
        except Exception as exc:
            log.warning("kgs_refill_failed", err=str(exc))
        await asyncio.sleep(60)

refill_task = asyncio.create_task(_refill_loop())
try:
    yield
finally:
    refill_task.cancel()
    # existing shutdown
```

Also fix the pool-key redis target: `next_short_code` takes the `cache_redis` param (`services/url_service.py:72`), but the conceptually-correct target is `app_redis` (durable app state). Pick one and use it everywhere; currently `spop` reads from the cache pool while the proposed refill writes to app pool → they won't match. Suggest **app_redis** for KGS state (evictable cache is the wrong TTL semantics for identifiers).

Fix `services/url_service.py:72` to receive `app_redis`:

```python
async def create_url(db, cache_redis, app_redis, *, user_id, workspace_id, body):
    ...
    code = short_code or await kgs_service.next_short_code(app_redis)
```

And in the router, `Depends(get_app_redis)` for that purpose.

---

### B8. Postgres `urls.click_count` is never written — column always 0
`app/models/url.py:59`, `app/routers/urls.py:33-46`

The router merges Redis `clicks:{code}` (live) with `row.click_count` (baseline). The baseline is never updated by any sweeper. The comment says "updated by periodic sweep or zero for now" — *no sweep exists anywhere in the repo*. After the Redis key hits its TTL (if you ever set one), or gets evicted, the counter resets to zero and analytics regresses. This is the 1M-clicks-reported-as-300-clicks bug.

**Options**:

1. Make the Redis counters **durable** (own Redis DB, no eviction, no TTL — redis-app seems intended for this).
2. Add a sweeper — the analytics-worker can read the ClickHouse hourly aggregate and `UPDATE urls SET click_count = click_count + ? WHERE short_code IN (...)`. Leave the Redis key for live reads only.

Minimal fix path: change `_merge_click_counts` to read from ClickHouse aggregate when Redis is missing, not silently return zero:

```python
# services/analytics_service.py  (new helper)
async def click_totals(ch, short_codes: list[str]) -> dict[str, int]:
    if not short_codes:
        return {}
    rows = await _rows(
        ch,
        "SELECT short_code, count() FROM clicks WHERE short_code IN {codes:Array(String)} GROUP BY short_code",
        codes=short_codes,
    )
    return {r[0]: int(r[1]) for r in rows}
```

Then in `urls.py:_merge_click_counts`, use this when `live is None`. Document that ClickHouse is the source of truth for totals.

---

### B9. `_merge_click_counts` issues a pipeline per page but ignores TTL staleness
`app/routers/urls.py:29-61`

This is the designed hot path. Two issues:

1. `from datetime import ...` inside the loop (line 56) — import moved to module top.
2. `int(live)` raises if someone writes a non-integer; wrap defensively.
3. `get(f"clicks:last:{c}")` — inside a loop; with 200-per-page, this is 400 Redis round-trips but at least they're pipelined. Confirm `cache.pipeline()` on `redis.asyncio` does auto-transaction=False with a single RESP write (it does).

No blocker — move the import.

---

### B10. `users/me` `PATCH` mutates user in a request where auth resolves user via a different session? No — same session — OK, but `db.refresh(user)` is called after `db.flush()` *before* the dep layer's commit. `get_session` commits at the end, so refresh sees the pre-commit state. It works, but consider explicitly committing inside the service for clarity. Not a blocker.

---

### B11. `services/api_key_service.revoke_api_key` deletes key, then evicts `apikey:{digest}` — but no writer populates `apikey:{digest}`
`app/services/api_key_service.py:65-68`

`deps.get_current_user` never caches API keys in Redis — it hits Postgres on every request. The `redis.delete(f"apikey:{digest}")` is a no-op and the inline comment is misleading. Either implement a write-through cache (each auth hit SETEX `apikey:{digest}` with the `User` id for 60s) or remove this dead code. Cost of lookup: each authenticated API-key request pays an extra `SELECT user` + `SELECT api_key` round-trip; for high-throughput programmatic clients this is measurable.

**Recommend**: add a 60s Redis cache in `deps.get_current_user` (API-key branch) and make `revoke_api_key`'s delete real.

---

### B12. `domain_service.create_domain` doesn't refresh after IntegrityError-rollback corruption
`app/services/domain_service.py:22-23`

When `IntegrityError` is caught, we raise `Conflict` but never roll back the session. The outer dep *will* rollback on exception propagation, which is correct — except the `refresh(row)` on the success path on line 24 happens on a row whose transaction state is fine. No actual bug but the failure path leaks an uncommitted savepoint if other ops had flushed first. Wrap the flush in `db.begin_nested()` as per B2.

---

### B13. `auth_service.register_user` — race window where slug check then insert is non-atomic
`app/services/auth_service.py:68-71`

```python
while await db.scalar(select(Workspace).where(Workspace.slug == slug)):
    suffix += 1
    slug = f"{base_slug}-{suffix}"
```

Two simultaneous signups with the same local-part can both pass this check and hit the UNIQUE constraint. Not fatal (IntegrityError handler returns 409) but the 409 says "Resource conflict" and the user re-tries. Acceptable for now; note it. If you care, use a SAVEPOINT + retry.

---

## 2. HIGH-IMPACT OPTIMIZATIONS

### H1. `ilike` on `long_url` — missing trigram index
`app/services/url_service.py:134-136`, migration 001:121-122

```python
base = base.where((Url.short_code.ilike(like)) | (Url.long_url.ilike(like)))
```

With `search="%foo%"`, Postgres **cannot** use `idx_urls_long_url_hash` (md5 equality only) nor any btree. `pg_trgm` is installed (init.sql:11) but there is no GIN trigram index on `long_url`. At 1M rows this becomes a seqscan on every `list_urls` with a search.

**Patch** — add a new migration:

```python
# alembic/versions/002_add_long_url_trgm.py
def upgrade():
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_urls_long_url_trgm
        ON urls USING gin (long_url gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_urls_short_code_trgm
        ON urls USING gin (short_code gin_trgm_ops)
    """)
```

Then `list_urls` with `ILIKE %foo%` drops from ~seconds to ~ms on 1M rows.

---

### H2. `list_urls` counts via `SELECT count() FROM (subquery)` — expensive
`app/services/url_service.py:138-139`

The `select(func.count()).select_from(base.subquery())` wraps the filter, executes twice (once for count, once for rows), and cannot use a covering index well. For the common "my URLs, page 1" case, an approximation or a materialized count would help.

**Patch** — for unfiltered lists, use `EXPLAIN`-based estimate from `pg_class.reltuples` or a background-maintained counter. For filtered lists, use `count() OVER()` as a window function in the same query:

```python
from sqlalchemy import over, select, func

stmt = (
    select(Url, func.count().over().label("_total"))
    .where(...)
    .order_by(Url.created_at.desc())
    .offset(offset).limit(limit)
)
result = (await db.execute(stmt)).all()
rows = [r[0] for r in result]
total = int(result[0][1]) if result else 0
```

One query instead of two → ~½ the planner/parse cost, better cache locality.

---

### H3. `ORJSONResponse` set as default — good. But `JSONResponse` is still used by the rate limiter
`app/main.py:58` ✓ default is ORJSON.
`app/middleware/rate_limiter.py:17,87,109` — uses default `starlette.responses.JSONResponse`.

Switch to `ORJSONResponse` (5-10× faster for 429 payloads under spike load). See B4.

---

### H4. Webhook dispatch creates a new `httpx.AsyncClient` per call
`app/services/webhook_service.py:104`

```python
async with httpx.AsyncClient(timeout=5.0, http2=True) as client:
    resp = await client.post(...)
```

Per-call client creation means a TCP/TLS handshake per webhook send — 10-100× the latency of a reused pool. The retry loop makes it worse (3 handshakes per attempt).

**Patch** — module-level client:

```python
# services/webhook_service.py
_http_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=5.0, http2=True)
    return _http_client

async def dispatch(webhook, event, data):
    ...
    client = get_http_client()
    async for attempt in AsyncRetrying(...):
        with attempt:
            resp = await client.post(webhook.url, content=body, headers=headers)
            resp.raise_for_status()
```

And close it in `main.py` lifespan. Same treatment applies to `safe_browsing.py:37`.

---

### H5. `dispatch_background` leaks tasks (no reference kept, no error logging)
`app/services/webhook_service.py:111-113`

```python
def dispatch_background(webhook, event, data):
    asyncio.create_task(dispatch(webhook, event, data))
```

The returned task is not retained — Python may GC it mid-flight (in CPython this rarely happens but is [officially a footgun](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task)). Keep a WeakSet of background tasks or wrap with `asyncio.shield`:

```python
_background_tasks: set[asyncio.Task] = set()

def dispatch_background(webhook, event, data):
    t = asyncio.create_task(dispatch(webhook, event, data))
    _background_tasks.add(t)
    t.add_done_callback(_background_tasks.discard)
```

---

### H6. Rate-limit Lua uses two KEYS/ARGV round-trips per request (default + plan)
`app/middleware/rate_limiter.py:82-106`

The middleware does two `EVALSHA` calls sequentially. Pipeline them (or merge into one Lua script that takes both buckets). At 1k req/s, that's 2 Redis RTTs per request; pipelining halves it.

**Patch**:

```python
pipe = redis.pipeline(transaction=False)
pipe.evalsha(self._sha, 1, default_key, now_ms, 60_000, self.default_per_min)
if bucket:
    pipe.evalsha(self._sha, 1, plan_key, now_ms, window_ms, limit)
[(allowed, cur), *rest] = await pipe.execute()
```

(requires reshuffle of the code — see patch block in next section.)

---

### H7. `CORSMiddleware` `allow_origins` with `allow_credentials=True`
`app/main.py:67-73`

`cors_origins` defaults to empty list (config.py:42). In dev, devs set `CORS_ORIGINS=*`, and `allow_credentials=True` + `allow_origins=["*"]` is a **spec-violating, unsafe combo** — browsers reject it and Starlette warns. Validate in config: if any origin is `*`, force `allow_credentials=False`.

**Patch** in `app/main.py`:

```python
if settings.cors_origins:
    creds = "*" not in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=creds,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    )
```

`allow_methods=["*"]` and `allow_headers=["*"]` also conflict with `allow_credentials=True`.

---

### H8. `api_keys` listing — N+1 opportunity on JWT path (each request hits both `User` and `ApiKey`)
`app/deps.py:100-105`

Not a true N+1 but it's two round-trips per authenticated call. Join them:

```python
stmt = (
    select(User, ApiKey)
    .join(ApiKey, ApiKey.user_id == User.id)
    .where(ApiKey.key_hash == digest, ApiKey.is_active.is_(True), User.is_active.is_(True))
)
row = (await db.execute(stmt)).first()
```

One RTT instead of two on every API-key request.

---

### H9. `db.refresh(row)` after every write — one extra SELECT per create/update
`services/url_service.py:99, 166; domain_service.py:24, 60; api_key_service.py:38`

SQLAlchemy with `expire_on_commit=False` (database.py:37) means committed attributes remain usable. You only need `refresh` if you rely on DB-server-assigned defaults you didn't already set (e.g. `updated_at`). For `URLOut` the response includes `created_at` and `updated_at` — both set by `server_default=func.now()`. The flush populates `id` via RETURNING for Postgres/asyncpg — but not `created_at` / `updated_at` unless explicit.

**Patch options**:
1. Keep the `refresh` (works, extra SELECT).
2. Use `mapper.eager_defaults = True` or set `server_default` + `onupdate` and include them in INSERT's RETURNING. With `insertmanyvalues` on asyncpg this is cheap.

Option 2 is cleanest:

```python
# models/base.py — add class-level hint
class UUIDPrimaryKeyMixin:
    __mapper_args__ = {"eager_defaults": True}
```

Then drop the `db.refresh()` calls. Saves 1 round-trip per write.

---

### H10. Pydantic `model_validate(row)` with ORM — good choice (v2 fast path). Confirmed ✓
All `URLOut.model_validate(row)` invocations use `from_attributes=True` — this is the cheap path.

---

### H11. Health endpoint creates a fresh session per check
`app/routers/health.py:20`

```python
async with database.SessionLocal() as s:
    await s.execute(text("SELECT 1"))
```

Acceptable for /health, but /health is polled every 5-10s by orchestrators. Use `engine.connect()` directly to skip session setup:

```python
async with database.engine.connect() as conn:
    await conn.execute(text("SELECT 1"))
```

Minor. Nice-to-have.

---

## 3. ARCHITECTURE CLEANUPS (deferrable)

### A1. Alembic migration drift from `init.sql`
`alembic/versions/001_initial.py` vs `infrastructure/db/init.sql`

Differences:
- init.sql creates `trg_*_updated_at` PL/pgSQL triggers + `set_updated_at()` function. Alembic migration does **not**. On an Alembic-only bootstrap, `updated_at` will never auto-bump on UPDATE. Python ORM's `onupdate=func.now()` covers the happy path, but any SQL-level UPDATE (psql, bulk jobs) breaks.
- init.sql has `idx_urls_short_code` (unique index). Alembic relies on the `unique=True` in `short_code` column — same effect but index name differs from init.sql. Tests that assert on `pg_indexes` will flake.
- init.sql uses `DEFAULT 'free'`; Alembic uses `server_default="free"` → both become `'free'::varchar` — fine.

**Fix**: add the trigger function + triggers to the Alembic migration:

```python
# alembic/versions/001_initial.py — at the end of upgrade()
op.execute("""
    CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
    BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
    $$ LANGUAGE plpgsql;
""")
for table in ("users", "workspaces", "domains", "urls", "api_keys", "webhooks"):
    op.execute(f"""
        DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
        CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)
```

Also create the explicit `idx_urls_short_code` unique index so names line up.

---

### A2. `get_db` wraps `get_session` with no added behavior
`app/deps.py:38-39`

```python
async def get_db(session = Depends(get_session)) -> AsyncSession:
    return session
```

Useless indirection. Remove and let routers depend on `get_session` directly. Saves one frame per request and one grep hop.

---

### A3. Every router builds its own `Meta(...).model_dump()` manually
Call sites: `routers/urls.py:108`, `users.py:53`, `api_keys.py:64`, `domains.py:50`, `webhooks.py:52`.

Use the existing `ok(data, meta)` helper from `schemas/common.py:53`:

```python
return ok(
    await _merge_click_counts(app_redis, list(rows)),
    Meta(page=pag.page, per_page=pag.per_page, total=total),
)
```

---

### A4. `request.state.auth` set in `get_current_user` but `plan` never propagated
`app/deps.py:94`, `middleware/rate_limiter.py:100-103`

The middleware tries to read `auth.plan` to apply per-plan limits, but `get_current_user` stores `{"type": "jwt", "payload": payload, "user_id": ...}` without `plan`. Plan lives in `payload["plan"]`, so the middleware reads `None` and always falls back to `"free"`. *Every user is rate-limited as free*, including paying enterprise customers.

Also, `BaseHTTPMiddleware` runs **before** dependencies resolve (it wraps the route, but Depends runs after middleware). So `request.state.auth` is *never set* at rate-limit time. The middleware cannot see the auth result — it can only read the Bearer/X-API-Key header and decode it itself.

**Patch** — decode in the middleware (cheaply, cached):

```python
from app.services import jwt_service

def _plan_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            p = jwt_service.decode(auth.split(" ", 1)[1])
            return p.get("plan", "free")
        except Exception:
            pass
    return "free"
```

Call once per request in `dispatch`.

This is a bit expensive (JWT decode per req) — cache by raw token in an LRU for 30s.

---

### A5. `click_count` type inconsistency
`models/url.py:59` — `BigInteger` DB type, but `URLOut.click_count: int`. Python int is unbounded, fine. But `_merge_click_counts` does `int(row.click_count or 0)` which is redundant (it's already int). Minor.

---

### A6. Logging: passwords / refresh tokens potentially leaked on 500
`app/exceptions.py:117-123`

`_catch_all` calls `log.exception("unhandled_exception", path=..., err=str(exc))`. Pydantic `RequestValidationError` handler uses `exc.errors()` which includes the raw input value — for `RegisterIn` / `LoginIn` that means **the user's password goes into the 422 log line**.

**Patch** — scrub `input` from validation errors:

```python
# exceptions.py  _validation handler
def _scrub(errs):
    out = []
    for e in errs:
        e = dict(e)
        e.pop("input", None)
        e.pop("ctx", None)
        out.append(e)
    return out

async def _validation(_: Request, exc: RequestValidationError):
    return ORJSONResponse(
        status_code=422,
        content=_envelope("VALIDATION_ERROR", "Invalid payload", details=_scrub(exc.errors())),
    )
```

---

### A7. `jwt_service.issue_access` sets `workspace_id` in the payload but `deps.get_current_user` never uses it
Look at `deps.py:69-95` — no reference to `workspace_id` from the payload. So `get_current_workspace` does a fresh DB lookup every call to resolve the primary workspace. Cache the workspace id in the JWT → skip the SELECT.

**Patch** in `deps.get_current_workspace`:

```python
async def get_current_workspace(
    request: Request,
    user = Depends(get_current_user),
    db = Depends(get_db),
) -> Workspace:
    auth = getattr(request.state, "auth", {})
    ws_id = (auth.get("payload") or {}).get("workspace_id")
    if ws_id:
        ws = await db.get(Workspace, UUID(ws_id))
        if ws and ws.owner_id == user.id:
            return ws
    ws = await db.scalar(select(Workspace).where(Workspace.owner_id == user.id).limit(1))
    if not ws:
        raise HTTPException(403, "No workspace bound to user")
    return ws
```

Drops one SELECT per analytics/webhooks/domains/workspace-scoped request.

---

### A8. `short_code_pool` table defined in the ORM but never read/written by the app
`app/models/short_code_pool.py` — dead Python code. KGS uses Redis only. Either delete the model + table, or implement DB-backed claim (a different design). Currently it's a schema bug magnet.

---

### A9. No request-size limit
FastAPI relies on the ASGI server. Add a `Content-Length` check in RateLimit or a dedicated middleware (bulk_create up to 1000 URLs @ 10KB each ≈ 10MB per call; current defaults let this through). Reject payloads > 2MB at the edge (nginx) or app (middleware).

---

### A10. `services/auth_service.refresh_tokens` — `redis.delete` returns 1 iff key existed, but race-allows two concurrent valid refreshes
`services/auth_service.py:134-136` — single-use via `DEL`. Under contention (double-submit), both `DEL` calls race but `DEL` is atomic → exactly one succeeds. ✓ Correct. Keep.

---

## Priority Summary for Fixer

| Item | File | Severity |
|------|------|----------|
| B1   | routers/urls.py:23                    | **BLOCKER** |
| B2   | services/url_service.py:89            | **BLOCKER** |
| B3   | routers/urls.py:158                   | **BLOCKER** |
| B4   | middleware/rate_limiter.py:87,109; exceptions.py:87 | **BLOCKER** |
| B5   | middleware/rate_limiter.py:67         | **BLOCKER** |
| B7   | main.py lifespan; services/kgs_service.py | **BLOCKER** |
| B8   | routers/urls.py:29; new sweeper       | **BLOCKER** |
| B11  | services/api_key_service.py:65        | HIGH |
| H1   | alembic/versions/002_add_long_url_trgm.py (new) | HIGH |
| H2   | services/url_service.py:138           | HIGH |
| H4   | services/webhook_service.py:104; safe_browsing.py:37 | HIGH |
| H6   | middleware/rate_limiter.py:82         | HIGH |
| H7   | main.py:67                            | HIGH |
| H8   | deps.py:100                           | HIGH |
| H9   | models/base.py (eager_defaults)       | HIGH |
| A1   | alembic/versions/001_initial.py       | MED |
| A2-A10 | see sections                        | MED |

— RV8
