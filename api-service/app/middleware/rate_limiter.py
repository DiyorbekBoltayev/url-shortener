"""Redis-backed sliding-window rate limiter.

Keyed on API key when present, otherwise the (proxy-aware) client IP.

Per-plan limits (HLA 7):
    free    :  10/hour   POST /urls      30/min analytics
    pro     : 100/hour   POST /urls     100/min analytics
    business: 1000/hour  POST /urls     500/min analytics
    enterprise: 10000/hour            unlimited
"""
from __future__ import annotations

import time

from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app import redis_client
from app.logging import get_logger

log = get_logger(__name__)

_LUA = """
local key, now, win, limit = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - win)
local cur = redis.call('ZCARD', key)
if cur >= limit then return {0, cur} end
redis.call('ZADD', key, now, now .. ':' .. math.random())
redis.call('PEXPIRE', key, win)
return {1, cur + 1}
"""


def _match_bucket(path: str, method: str) -> tuple[str, int] | None:
    """Return a ``(bucket_name, window_ms)`` for endpoints we limit, else None.

    Auth endpoints (login/register) get a tight per-IP bucket to blunt
    credential-stuffing and registration-spam (RV10 1.3). They intentionally
    keep the same 5/min cap across all plans because the caller is
    pre-authentication and plan state is unknown.
    """
    # --- auth (per-IP, pre-auth) ---
    if method == "POST" and path.endswith("/api/v1/auth/login"):
        return ("auth_login", 60_000)
    if method == "POST" and path.endswith("/api/v1/auth/register"):
        return ("auth_register", 60_000)
    # --- authenticated buckets ---
    if method == "POST" and path.endswith("/api/v1/urls"):
        return ("create_urls", 3_600_000)
    if path.startswith("/api/v1/analytics"):
        return ("analytics", 60_000)
    return None


_DEFAULT_LIMITS: dict[str, dict[str, int]] = {
    # Auth buckets are intentionally flat across plans: this bucket runs
    # before authentication, so we cannot key by plan. 5/min/IP is the
    # RV10 1.3 recommendation.
    "auth_login":    {"free": 5,  "pro": 5,   "business": 5,    "enterprise": 5},
    "auth_register": {"free": 5,  "pro": 5,   "business": 5,    "enterprise": 5},
    "create_urls":   {"free": 10, "pro": 100, "business": 1000, "enterprise": 10_000},
    "analytics":     {"free": 30, "pro": 100, "business": 500,  "enterprise": 1_000_000},
}

# Auth buckets are ALWAYS keyed by client IP, regardless of any supplied
# ``X-API-Key`` header — otherwise an attacker could rotate through keys to
# bypass the limit during credential stuffing.
_IP_ONLY_BUCKETS: frozenset[str] = frozenset({"auth_login", "auth_register"})


def _rate_limit_response(retry_after: int, message: str) -> ORJSONResponse:
    """Build the canonical 429 envelope — matches `_envelope` in exceptions."""
    return ORJSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        content={
            "success": False,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": message,
                "retry_after": retry_after,
            },
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, default_per_min: int = 120) -> None:
        super().__init__(app)
        self.default_per_min = default_per_min
        self._sha: str | None = None

    async def _ensure_sha(self, redis) -> str:
        if self._sha is None:
            self._sha = await redis.script_load(_LUA)
        return self._sha

    async def _eval(self, redis, key: str, now_ms: int, window_ms: int, limit: int):
        sha = await self._ensure_sha(redis)
        try:
            return await redis.evalsha(sha, 1, key, now_ms, window_ms, limit)
        except Exception:
            # Script cache flushed — reload once and retry.
            self._sha = await redis.script_load(_LUA)
            return await redis.evalsha(self._sha, 1, key, now_ms, window_ms, limit)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        # Skip CORS preflights + infra probes. Preflights must always 2xx
        # so CORS negotiation works.
        if (
            request.method == "OPTIONS"
            or request.url.path in {"/health", "/ready", "/metrics"}
        ):
            return await call_next(request)

        try:
            redis = redis_client.get_app_redis()
        except RuntimeError:
            return await call_next(request)

        ident = request.headers.get("X-API-Key") or (
            request.client.host if request.client else "anon"
        )
        bucket = _match_bucket(request.url.path, request.method)

        now_ms = int(time.time() * 1000)
        default_key = f"rl:default:{ident}:{request.url.path}"

        # Pre-compute the plan bucket key / limit so we can pipeline both
        # evalsha calls into one Redis round-trip.
        plan_key: str | None = None
        plan_window = 0
        plan_limit = 0
        if bucket:
            name, plan_window = bucket
            plan = "free"
            auth = getattr(request.state, "auth", None)
            if isinstance(auth, dict):
                plan = auth.get("plan") or (
                    (auth.get("payload") or {}).get("plan", "free")
                )
            plan_limit = _DEFAULT_LIMITS[name].get(
                plan, _DEFAULT_LIMITS[name]["free"]
            )
            if name in _IP_ONLY_BUCKETS:
                bucket_ident = (
                    request.client.host if request.client else "anon"
                )
            else:
                bucket_ident = ident
            plan_key = f"rl:{name}:{bucket_ident}"

        try:
            sha = await self._ensure_sha(redis)
            pipe = redis.pipeline(transaction=False)
            pipe.evalsha(
                sha, 1, default_key, now_ms, 60_000, self.default_per_min
            )
            if plan_key:
                pipe.evalsha(
                    sha, 1, plan_key, now_ms, plan_window, plan_limit
                )
            results = await pipe.execute()
        except Exception:
            # Script cache flushed or pipeline hiccup — serial fallback.
            results = [
                await self._eval(
                    redis, default_key, now_ms, 60_000, self.default_per_min
                )
            ]
            if plan_key:
                results.append(
                    await self._eval(
                        redis, plan_key, now_ms, plan_window, plan_limit
                    )
                )

        allowed, cur = results[0]
        if not allowed:
            return _rate_limit_response(60, "Too many requests")

        if plan_key and len(results) > 1:
            allowed2, _ = results[1]
            if not allowed2:
                retry = max(1, plan_window // 1000)
                return _rate_limit_response(retry, "Plan limit reached")

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.default_per_min)
        try:
            response.headers["X-RateLimit-Remaining"] = str(
                max(self.default_per_min - int(cur), 0)
            )
        except (ValueError, TypeError):
            pass
        return response
