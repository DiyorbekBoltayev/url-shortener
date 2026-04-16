# RV3 — api-service (FastAPI) Review

**Target:** `C:\Users\User\Desktop\work\url-shortener\api-service\`
**Reviewer:** RV3
**Date:** 2026-04-14
**Contract:** `INTEGRATION_CONTRACT.md` (sections 2, 4, 7, 8, 9, 10, 12)
**Spec:** `research/05-HLA-high-level-architecture.md` §2.2, 3.1, 4, 7, 8
**Verdict:** **APPROVED with minor follow-ups.** No blockers found. Service is solid and contract-conformant.

---

## 1. Blocker checks — all PASS

| # | Check | Result | Evidence |
|---|---|---|---|
| B1 | Banned deps (`python-jose` / `passlib`) | PASS | `pyproject.toml` L19-20: `pyjwt[crypto]>=2.9,<3`, `pwdlib[argon2,bcrypt]>=0.2,<0.3`. No `python-jose` nor `passlib` anywhere in the tree. |
| B2 | Lifespan instead of deprecated `on_event` | PASS | `app/main.py` L34-51 uses `@asynccontextmanager` + `lifespan=` kwarg. No `on_event` in the repo. |
| B3 | Async session/engine hygiene | PASS | `app/database.py`: `create_async_engine` with `asyncpg`, `async_sessionmaker(expire_on_commit=False)`, `get_session` uses `async with`, commits on success, rolls back on exception. No `asyncio.run` in handlers; no sync engine leakage. |
| B4 | Alembic env.py async-aware | PASS | `alembic/env.py` uses `async_engine_from_config` + `connection.run_sync(_do_run_migrations)`, wrapped by `asyncio.run`. Offline branch uses URL literal binds (fine — no live connection). |
| B5 | Password hashing | PASS | `app/services/auth_service.py` L9-20 uses `pwdlib.PasswordHash.recommended()` (argon2 primary, bcrypt verifier). No plaintext. `verify_password` wraps in try/except → no user-typed-password DoS. |
| B6 | JWT claims + refresh rotation + secret handling | PASS | `app/services/jwt_service.py` adds `iat`, `exp`, `sub`, `jti`, `type`; `decode()` enforces `require=["exp","iat","sub","jti","type"]`. Refresh rotation is **single-use**: `auth_service.refresh_tokens` does `redis.delete(...)` on the jti and rejects when it returns 0 (good). Access revocation via `revoked:<jti>` with TTL. `JWT_SECRET` is a `SecretStr` in settings; dev default present but `.env.example` path is the operator’s responsibility. No secret checked into code other than the literal dev placeholder. |
| B7 | Rate limiter — real Redis + Lua + atomic | PASS | `app/middleware/rate_limiter.py`: sliding-window via `ZREMRANGEBYSCORE`/`ZCARD`/`ZADD` in a single Lua script, cached via `script_load`/`evalsha` with `NOSCRIPT` fallback. Per-plan buckets resolve plan from `request.state.auth`. Keyed on API key or client IP. |
| B8 | URL scheme whitelist / CRLF | PASS | `app/utils/url_validator.py`: `ALLOWED_SCHEMES={"http","https"}`, explicit CR/LF reject, max length 10 000, netloc required. Tests in `tests/test_urls.py` cover `javascript:` and CRLF rejection. |
| B9 | SQLi risk | PASS | SQLAlchemy ORM throughout. No `text(f"...")` with user input anywhere. `app/routers/health.py` uses `text("SELECT 1")` — constant only. `text(f"md5(long_url)")`-style calls in Alembic are static migration SQL. |
| B10 | API-key lookup hashed, not plaintext compared | PASS | `app/utils/hashing.py::hash_key` = sha256-hex; `app/deps.py::get_current_user` computes `digest = hash_key(raw_api_key)` then `WHERE key_hash == digest`. Storage likewise hashes-only; raw key returned to user exactly once at create time (`ApiKeyCreated.key`). |
| B11 | CORS `*` + credentials combo | PASS | `app/main.py` L66-73 only adds the CORS middleware when `settings.cors_origins` is a non-empty list (parsed from CSV env). Default is `[]` → middleware not installed. If the operator sets `CORS_ORIGINS=*` explicitly the combo becomes insecure, but the code itself does not ship that combo. **NIT:** consider rejecting literal `*` when `allow_credentials=True`. |
| B12 | Healthcheck covers PG + Redis | PASS | `app/routers/health.py` probes Postgres, redis-cache, redis-app, and ClickHouse (latter warn-only). Returns 503 when any of the three critical checks fail. Response shape matches contract §8: `{"status": "...", "checks": {...}}`. |
| B13 | Dockerfile hygiene | PASS | Multi-stage, `python:3.12-slim-bookworm` (pinned, not `:latest`), non-root `app:1000`, `HEALTHCHECK` present, `tini` as PID 1. `.env` is **not** copied into the image (only `app/`, `alembic/`, `alembic.ini`, `pyproject.toml`, optional `uv.lock`). `.env` is supplied at runtime via compose `env_file:`. |
| B14 | `updated_at` auto-update | PASS | `app/models/base.py::TimestampMixin` sets `onupdate=func.now()` on `updated_at`; inherited by every timestamped model. |
| B15 | Response envelope matches contract §7 | PASS | `app/schemas/common.py` defines `SuccessResponse` / `ErrorResponse` / `Meta` with the exact shape. All routers return `{"success": True, "data": ...}` (+ `meta` on list endpoints). `app/exceptions.py::_envelope` produces `{"success": False, "error": {"code", "message", ...}}`. Rate-limiter 429 responses also follow the envelope. |
| B16 | ClickHouse queries parameterised | PASS | `app/services/analytics_service.py` uses `{name:Type}` placeholders with `parameters=` throughout. `timeseries` interpolates `step` via `{step}` in an f-string — but `step` is only ever `toStartOfHour(ts)` or `toDate(ts)`, derived from a `Literal["hour","day"]` Pydantic type, never user-controlled. No injection surface. |
| B17 | Exception handlers | PASS | `app/exceptions.py::install_exception_handlers` wires `AppError`, `StarletteHTTPException`, `RequestValidationError`, `IntegrityError`, and catch-all `Exception`. All return envelope-conformant JSON. |
| B18 | Secrets in logs | PASS | `JWT_SECRET`, `webhook_signing_key`, `clickhouse_password`, `safe_browsing_api_key` are all `SecretStr`. No `.get_secret_value()` is routed through `log.*`. Logging config uses JSON renderer without any secret-bearing context. |

---

## 2. Nits / follow-ups (non-blocking)

1. **`pool_pre_ping`** — present (`database.py` L27). 
2. **Request ID middleware** — present (`middleware/request_id.py`), also binds to structlog contextvars. 
3. **Timing middleware** — present (`middleware/timing.py`) emits per-request access log + `X-Response-Time-Ms` header. 
4. **Prometheus instrumentator** — registered at `/metrics` in `main.py` L82 with `include_in_schema=False`. Matches contract §10. 
5. **OpenAPI tags** — every `include_router` call supplies a `tags=[...]`. 
6. **`urls.py::_primary_workspace_id` returns None** — workspace scoping on URL creation/listing falls back to user-id filtering. Works, but cross-workspace queries via JWT `workspace_id` claim are not implemented; worth a follow-up for multi-tenant correctness (spec §2.2). Not a security blocker because `get_url` / `list_urls` filter by `user_id`.
7. **Bulk create `errors` leaks internal message** — `tests/../urls.py::bulk_create` appends `str(exc)` to the response; consider mapping to a stable error code. Low impact.
8. **`delete_api_key` cache eviction key** — `apikey:{digest}` is used both here and in redirect-service; confirm the redirect-service reads that exact key.
9. **Webhook `dispatch_background`** — uses `asyncio.create_task` without a reference — task can be GC’d before completion on a busy loop. Consider a background-task registry or handing off to analytics-worker via Redis Streams.
10. **`health.py::/ready`** — returns a static `"ready"`. If you want K8s-style separation (liveness vs readiness), have `/ready` also probe the critical deps; `/health` could then be cheaper liveness. Optional.
11. **Alembic `001_initial`** — mirrors `infrastructure/db/init.sql`. Note that `idx_urls_tags` uses GIN and `idx_urls_long_url_hash` uses md5 — both postgres-specific, which is fine but the test suite’s sqlite fallback in `tests/conftest.py` swallows `create_all` errors (L113). Deep tests that rely on those indexes must run under testcontainers.
12. **Test coverage** — three test modules (`test_health`, `test_auth`, `test_urls`). `test_auth` auto-xfails under sqlite because of PG ARRAY; good safety net but real coverage requires `testcontainers[postgres]` (already a dev dep). Mark as follow-up.
13. **`deps.py::get_current_user`** fetches `get_app_redis()` *inside* the function (L82) rather than as a `Depends`. Works but makes DI-based overrides in tests harder. Low priority.
14. **`rate_limiter` SHA cache not scoped per-Redis-instance** — `self._sha` is module-scoped on the middleware instance. If the app ever talks to multiple Redis servers (e.g. during a swap), the cached SHA could be stale; the code already retries on failure. Fine.
15. **`urls.py::list_urls`** uses `ILIKE '%search%'` — unindexed. Consider the `pg_trgm` GIN index on `urls.long_url` (extension is already enabled in the Alembic migration).
16. **CORS literal `*` + credentials** — document in README that operators must not set `CORS_ORIGINS=*` in production.
17. **`jwt_service.issue_refresh`** does not carry the workspace/plan — that’s correct (refresh tokens should be minimal); just worth noting for any reviewer expecting full claims on refresh.

---

## 3. Contract conformance spot-check

| Contract item | Status |
|---|---|
| §2 service name `api-service`, internal port 8000 | PASS (`docker-compose.yml`, `EXPOSE 8000`) |
| §4 env var names (`DATABASE_URL`, `REDIS_CACHE_URL`, `REDIS_APP_URL`, `CLICKHOUSE_URL`, `CORS_ORIGINS`, `SAFE_BROWSING_API_KEY`, `JWT_SECRET`, `JWT_ACCESS_TTL_MIN`, `JWT_REFRESH_TTL_DAYS`) | PASS (`app/config.py`) |
| §7 response envelope | PASS |
| §8 `/health` shape & 503 semantics | PASS |
| §9 JSON structured logs (structlog) | PASS |
| §10 `/metrics` exposed | PASS |
| §12 version pins (FastAPI 0.115+, SQLAlchemy 2.0.44, Pydantic 2.11+, PyJWT 2.9+, pwdlib, redis-py 5.2, clickhouse-connect 0.8.10+) | PASS |

---

## 4. Final recommendation

**Ship it.** Zero blockers. Follow-ups #6 (workspace scoping), #9 (webhook task handling), and #12 (real PG testcontainers run) are the highest-value polish items before GA.
