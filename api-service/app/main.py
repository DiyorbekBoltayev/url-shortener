"""FastAPI application factory + lifespan."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select, text

from app import __version__, clickhouse_client, database, redis_client
from app.config import settings
from app.exceptions import install_exception_handlers
from app.logging import configure_logging, get_logger
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.timing import TimingMiddleware
from app.routers import (
    analytics,
    api_keys,
    auth,
    bulk_jobs,
    domains,
    folders,
    health,
    pixels,
    qr,
    urls,
    users,
    utm_templates,
    webhooks,
    workspaces,
)
from app import minio_client
from app.services import (
    bulk_jobs_service,
    kgs_service,
    og_fetcher,
    safety_service,
    url_service as _url_service,
    webhook_service,
)


log = get_logger(__name__)

# Internal refill knobs
_KGS_REFILL_INTERVAL_S = 60
_KGS_POOL_MIN = 100
_KGS_POOL_BATCH = 500

# Click sweeper — flush Redis counters into Postgres every 30s
_CLICK_SWEEP_INTERVAL_S = 30
_CLICK_SCAN_BATCH = 200

# S4 background workers ------------------------------------------------
# All three loops use Redis BLPOP with the same timeout so cancellation
# (SIGTERM → lifespan shutdown) unblocks within the timeout window.
_QUEUE_BLPOP_TIMEOUT_S = 5
# Back-off after an unhandled failure — gives upstream (Redis / DB) a
# moment to recover rather than hot-looping and spamming logs.
_WORKER_BACKOFF_S = 1.0
# Cap on graceful drain during shutdown so SIGTERM doesn't linger.
_SHUTDOWN_DRAIN_S = 5.0


async def _kgs_refill_loop() -> None:
    """Keep the KGS Redis pool topped up.

    Sleeps for :data:`_KGS_REFILL_INTERVAL_S` between checks; refills when
    the pool drops below :data:`_KGS_POOL_MIN`.
    """
    while True:
        try:
            redis = redis_client.get_app_redis()
            size = await kgs_service.pool_size(redis)
            if size < _KGS_POOL_MIN:
                added = await kgs_service.refill_pool(
                    redis, batch=_KGS_POOL_BATCH
                )
                log.info("kgs_pool_refilled", added=added, size_before=size)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("kgs_refill_failed", err=str(exc))
        try:
            await asyncio.sleep(_KGS_REFILL_INTERVAL_S)
        except asyncio.CancelledError:
            raise


async def _click_sweep_loop() -> None:
    """Drain Redis ``clicks:{code}`` counters into ``urls.click_count``.

    Uses ``SCAN`` to avoid a blocking ``KEYS``. For each counter we do
    ``GETSET clicks:{code} 0`` (atomic) to snapshot+reset so concurrent
    INCRs are never lost.  Last-clicked timestamp is best-effort: we
    only bump it when the current DB value is older.
    """
    while True:
        try:
            # redirect-service writes ``clicks:{code}`` counters into the
            # app-redis (shared app state), not the per-request cache redis.
            # Previous revisions pointed at cache_redis and silently saw 0
            # keys forever. See INTEGRATION_CONTRACT.md #5.
            cache = redis_client.get_app_redis()
            engine = database.engine
            if engine is None:
                await asyncio.sleep(_CLICK_SWEEP_INTERVAL_S)
                continue
            codes_to_flush: list[tuple[str, int]] = []
            cursor = 0
            # One SCAN pass per tick; capped at a reasonable batch size.
            while True:
                cursor, keys = await cache.scan(
                    cursor=cursor,
                    match="clicks:*",
                    count=_CLICK_SCAN_BATCH,
                )
                for key in keys:
                    if not isinstance(key, str):
                        key = key.decode()
                    # skip last-clicked side-channel
                    if key.startswith("clicks:last:"):
                        continue
                    code = key.split("clicks:", 1)[1]
                    # GETSET atomically reads + resets the counter.
                    prev = await cache.getset(key, 0)
                    try:
                        delta = int(prev) if prev is not None else 0
                    except (ValueError, TypeError):
                        delta = 0
                    if delta:
                        codes_to_flush.append((code, delta))
                if cursor == 0:
                    break

            if codes_to_flush:
                # Batch UPDATE via a VALUES() CTE. Cast each column in the
                # first VALUES row so asyncpg knows the parameter types —
                # otherwise it infers from row-1 and fails on (text, int)
                # ambiguity when rows > 1. Use CAST(... AS ...) rather than
                # `::` so SQLAlchemy named-param substitution doesn't collide
                # with Postgres cast syntax.
                parts: list[str] = []
                for i in range(len(codes_to_flush)):
                    if i == 0:
                        parts.append(
                            f"(CAST(:c{i} AS text), CAST(:d{i} AS bigint))"
                        )
                    else:
                        parts.append(f"(:c{i}, :d{i})")
                values_sql = ",".join(parts)
                params: dict[str, object] = {}
                for i, (code, delta) in enumerate(codes_to_flush):
                    params[f"c{i}"] = str(code)
                    params[f"d{i}"] = int(delta)
                sql = text(
                    f"""
                    WITH updates(short_code, delta) AS (
                        VALUES {values_sql}
                    )
                    UPDATE urls
                       SET click_count   = urls.click_count + updates.delta,
                           last_clicked_at = COALESCE(NOW(), urls.last_clicked_at)
                      FROM updates
                     WHERE urls.short_code = updates.short_code
                    """
                )
                async with engine.begin() as conn:
                    await conn.execute(sql, params)
                log.debug(
                    "click_sweep_flushed",
                    rows=len(codes_to_flush),
                    total=sum(d for _, d in codes_to_flush),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("click_sweep_failed", err=str(exc))
        try:
            await asyncio.sleep(_CLICK_SWEEP_INTERVAL_S)
        except asyncio.CancelledError:
            raise


async def _blpop_one(queue: str) -> str | None:
    """BLPOP wrapper. Returns the payload or ``None`` on timeout."""
    app_redis = redis_client.get_app_redis()
    result = await app_redis.blpop(queue, timeout=_QUEUE_BLPOP_TIMEOUT_S)
    if not result:
        return None
    # redis-py returns (key, value); ``decode_responses=True`` is set on
    # init so both are plain strings.
    _key, value = result
    return value


async def _og_fetch_loop() -> None:
    """Consume ``og:fetch:queue`` and persist OG metadata on ``urls``.

    Errors (network, parse, DB) are logged and swallowed so a single bad
    page cannot stall the pipeline.
    """
    while True:
        try:
            payload = await _blpop_one(_url_service.OG_FETCH_QUEUE)
            if payload is None:
                continue
            try:
                url_id = UUID(payload)
            except (TypeError, ValueError):
                log.warning("og_fetch_bad_payload", payload=payload)
                continue
            await _process_og_job(url_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("og_fetch_loop_error", err=str(exc))
            await asyncio.sleep(_WORKER_BACKOFF_S)


async def _process_og_job(url_id: UUID) -> None:
    from app.models.url import Url

    if database.SessionLocal is None:
        return
    async with database.SessionLocal() as db:
        row = await db.scalar(select(Url).where(Url.id == url_id))
        if row is None or not row.preview_enabled:
            return
        long_url = row.long_url
    # Fetch outside the DB session so the HTTP round-trip doesn't hold
    # a connection open.
    result = await og_fetcher.fetch_og(long_url)
    if result is None:
        return
    async with database.SessionLocal() as db:
        row = await db.scalar(select(Url).where(Url.id == url_id))
        if row is None:
            return
        row.og_title = result.title
        row.og_description = result.description
        row.og_image_url = result.image_url
        row.favicon_url = result.favicon_url
        row.og_fetched_at = datetime.now(timezone.utc)
        await db.commit()
    log.info("og_fetch_done", url_id=str(url_id), has_title=bool(result.title))


async def _safety_scan_loop() -> None:
    """Consume ``safety:scan:queue`` and update ``urls.safety_status``."""
    while True:
        try:
            payload = await _blpop_one(_url_service.SAFETY_SCAN_QUEUE)
            if payload is None:
                continue
            try:
                url_id = UUID(payload)
            except (TypeError, ValueError):
                log.warning("safety_scan_bad_payload", payload=payload)
                continue
            await _process_safety_job(url_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("safety_scan_loop_error", err=str(exc))
            await asyncio.sleep(_WORKER_BACKOFF_S)


async def _process_safety_job(url_id: UUID) -> None:
    from app.models.url import Url

    if database.SessionLocal is None:
        return
    cache = redis_client.get_cache_redis()
    async with database.SessionLocal() as db:
        row = await db.scalar(select(Url).where(Url.id == url_id))
        if row is None:
            return
        long_url = row.long_url
    verdict = await safety_service.scan(long_url, cache=cache)
    async with database.SessionLocal() as db:
        row = await db.scalar(select(Url).where(Url.id == url_id))
        if row is None:
            return
        row.safety_status = verdict.status
        row.safety_reason = verdict.reason or None
        row.safety_checked_at = datetime.now(timezone.utc)
        await db.commit()
        # Refresh the Redis meta so redirect-service sees the new status.
        try:
            await cache.hset(
                f"url:meta:{row.short_code}",
                mapping={"safety_status": verdict.status},
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("safety_meta_refresh_failed", err=str(exc))


async def _bulk_jobs_loop() -> None:
    """Consume ``bulk:jobs:pending`` and dispatch per-kind handlers."""
    while True:
        try:
            payload = await _blpop_one(bulk_jobs_service.BULK_JOB_QUEUE)
            if payload is None:
                continue
            try:
                job_id = UUID(payload)
            except (TypeError, ValueError):
                log.warning("bulk_job_bad_payload", payload=payload)
                continue
            if database.SessionLocal is None:
                log.warning("bulk_job_no_db", job_id=str(job_id))
                continue
            await bulk_jobs_service.process_one(
                database.SessionLocal,
                redis_client.get_cache_redis(),
                redis_client.get_app_redis(),
                job_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("bulk_jobs_loop_error", err=str(exc))
            await asyncio.sleep(_WORKER_BACKOFF_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("startup_begin", env=settings.environment, version=__version__)
    database.init_engine()
    redis_client.init_redis()
    try:
        await clickhouse_client.init_clickhouse()
    except Exception as exc:  # noqa: BLE001
        log.warning("clickhouse_init_failed", err=str(exc))

    # Warm the KGS pool so the first POST /urls doesn't burn an extra
    # network round-trip generating a random code.
    try:
        redis = redis_client.get_app_redis()
        if await kgs_service.pool_size(redis) < _KGS_POOL_MIN:
            await kgs_service.refill_pool(redis, batch=_KGS_POOL_BATCH)
    except Exception as exc:  # noqa: BLE001
        log.warning("kgs_initial_refill_failed", err=str(exc))

    # Idempotently ensure the MinIO buckets exist so bulk export/import
    # don't error on a fresh deploy. Safe to skip when MinIO is offline —
    # the workers degrade gracefully.
    try:
        await minio_client.ensure_default_buckets()
    except Exception as exc:  # noqa: BLE001
        log.warning("minio_bootstrap_failed", err=str(exc))

    refill_task = asyncio.create_task(_kgs_refill_loop())
    sweep_task = asyncio.create_task(_click_sweep_loop())
    og_task = asyncio.create_task(_og_fetch_loop())
    safety_task = asyncio.create_task(_safety_scan_loop())
    bulk_task = asyncio.create_task(_bulk_jobs_loop())
    background_tasks: tuple[asyncio.Task, ...] = (
        refill_task, sweep_task, og_task, safety_task, bulk_task,
    )
    try:
        yield
    finally:
        log.info("shutdown_begin")
        for task in background_tasks:
            task.cancel()
        # Drain with a cap so shutdown completes even if a handler is
        # stuck on a slow upstream.
        try:
            await asyncio.wait_for(
                asyncio.gather(*background_tasks, return_exceptions=True),
                timeout=_SHUTDOWN_DRAIN_S,
            )
        except asyncio.TimeoutError:
            log.warning("shutdown_drain_timeout")
        await webhook_service.close_http_client()
        await clickhouse_client.close_clickhouse()
        await redis_client.close_redis()
        await database.dispose_engine()
        log.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="URL Shortener API",
        version=__version__,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # --- Middleware (outer -> inner) --------------------------------
    if settings.cors_origins:
        # Browsers reject `allow_credentials=True` + `*` origin; if the
        # config is wildcarded, downgrade credentials silently.
        allow_creds = "*" not in settings.cors_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=allow_creds,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-API-Key",
                "X-Request-ID",
            ],
        )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RateLimitMiddleware, default_per_min=settings.rl_default_per_min)

    # --- Exception handlers -----------------------------------------
    install_exception_handlers(app)

    # --- Prometheus ---------------------------------------------------
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    # --- Routers -----------------------------------------------------
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(urls.router, prefix="/api/v1/urls", tags=["urls"])
    # Public (no-auth) shorten — mounted separately so it lives at
    # `/api/v1/shorten` rather than `/api/v1/urls/shorten`.
    app.include_router(urls.public_router, prefix="/api/v1", tags=["public"])
    app.include_router(qr.router, prefix="/api/v1/urls", tags=["qr"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
    app.include_router(domains.router, prefix="/api/v1/domains", tags=["domains"])
    app.include_router(api_keys.router, prefix="/api/v1/api-keys", tags=["api-keys"])
    app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    # ---- P0 features ------------------------------------------------
    app.include_router(folders.router, prefix="/api/v1/folders", tags=["folders"])
    app.include_router(
        utm_templates.router,
        prefix="/api/v1/utm-templates",
        tags=["utm-templates"],
    )
    app.include_router(pixels.router, prefix="/api/v1/pixels", tags=["pixels"])
    # Link <-> pixel attach/detach colocated with the URL resource.
    app.include_router(
        pixels.urls_router, prefix="/api/v1/urls", tags=["pixels"]
    )
    app.include_router(
        workspaces.router, prefix="/api/v1/workspaces", tags=["workspaces"]
    )
    # /api/v1/auth/switch-workspace lives on the auth prefix.
    app.include_router(
        workspaces.auth_router, prefix="/api/v1/auth", tags=["workspaces"]
    )
    app.include_router(
        bulk_jobs.router, prefix="/api/v1/bulk-jobs", tags=["bulk-jobs"]
    )
    app.include_router(
        bulk_jobs.links_router, prefix="/api/v1/links", tags=["bulk-jobs"]
    )

    return app


app = create_app()
