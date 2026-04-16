"""Health + readiness endpoints (INTEGRATION_CONTRACT section 8)."""
from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app import clickhouse_client, database, redis_client

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def health(response: Response) -> dict[str, object]:
    checks: dict[str, str] = {}

    # Postgres -------------------------------------------------------
    try:
        if database.SessionLocal is None:
            raise RuntimeError("SessionLocal missing")
        async with database.SessionLocal() as s:
            await s.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"fail: {exc.__class__.__name__}"

    # Redis (cache) --------------------------------------------------
    try:
        r = redis_client.get_cache_redis()
        checks["redis"] = "ok" if await r.ping() else "fail"
    except Exception as exc:
        checks["redis"] = f"fail: {exc.__class__.__name__}"

    # Redis (app) ----------------------------------------------------
    try:
        ra = redis_client.get_app_redis()
        checks["redis_app"] = "ok" if await ra.ping() else "fail"
    except Exception as exc:
        checks["redis_app"] = f"fail: {exc.__class__.__name__}"

    # ClickHouse (best effort; warn-only) ----------------------------
    try:
        ch = clickhouse_client.get_clickhouse()
        res = await ch.query("SELECT 1")
        checks["clickhouse"] = "ok" if res else "fail"
    except Exception as exc:
        checks["clickhouse"] = f"fail: {exc.__class__.__name__}"

    critical = {"postgres", "redis", "redis_app"}
    ok = all(checks.get(k) == "ok" for k in critical)
    response.status_code = (
        status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return {"status": "ok" if ok else "degraded", "checks": checks}


@router.get("/ready", include_in_schema=False)
async def ready() -> dict[str, str]:
    return {"status": "ready"}
