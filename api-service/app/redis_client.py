"""Async Redis pools — one for URL cache, one for app state."""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

cache_redis: aioredis.Redis | None = None
app_redis: aioredis.Redis | None = None


def init_redis() -> None:
    """Create both Redis client pools idempotently."""
    global cache_redis, app_redis
    if cache_redis is None:
        cache_redis = aioredis.from_url(
            settings.redis_cache_url,
            decode_responses=True,
            max_connections=50,
        )
    if app_redis is None:
        app_redis = aioredis.from_url(
            settings.redis_app_url,
            decode_responses=True,
            max_connections=50,
        )


async def close_redis() -> None:
    global cache_redis, app_redis
    if cache_redis is not None:
        await cache_redis.aclose()
        cache_redis = None
    if app_redis is not None:
        await app_redis.aclose()
        app_redis = None


def get_cache_redis() -> aioredis.Redis:
    if cache_redis is None:
        raise RuntimeError("cache_redis is not initialised")
    return cache_redis


def get_app_redis() -> aioredis.Redis:
    if app_redis is None:
        raise RuntimeError("app_redis is not initialised")
    return app_redis
