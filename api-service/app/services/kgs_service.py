"""Key Generation Service — base62 + Redis-backed pool.

Strategy:
    1. Prefer a pre-generated code from Redis SET ``kgs:pool`` (SPOP).
    2. Fall back to a fresh random 7-char code.

The pool is warmed on startup (:func:`refill_pool`) and periodically by a
background task in :mod:`app.main`.

Pool state lives in ``app_redis`` (durable, no eviction) — NOT the cache
Redis, which may evict/TTL entries. Every caller must use the same
connection, which is why ``next_short_code`` and ``refill_pool`` both
accept a ``Redis`` argument.
"""
from __future__ import annotations

import secrets

from redis.asyncio import Redis

POOL_KEY = "kgs:pool"
COUNTER_KEY = "kgs:counter"
# offset makes sure encoded length >= 3 chars: 62**2 = 3844
_MIN_OFFSET = 238_328  # 62**3


async def next_short_code(redis: Redis) -> str:
    """Pop a code from the pool; else generate a fresh random code.

    Does *not* check Postgres uniqueness — the caller must flush and
    retry on IntegrityError.
    """
    try:
        popped = await redis.spop(POOL_KEY)
    except Exception:
        popped = None
    if popped:
        return popped if isinstance(popped, str) else popped.decode()
    return random_short_code(7)


def random_short_code(length: int = 7) -> str:
    """Last-resort random code (also used when the pool is empty)."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def pool_size(redis: Redis) -> int:
    try:
        return int(await redis.scard(POOL_KEY))
    except Exception:
        return 0


async def refill_pool(redis: Redis, *, batch: int = 500) -> int:
    """Seed the Redis pool with ``batch`` fresh random codes.

    Uniqueness is best-effort — any collisions at insert time are retried
    by the URL service via SAVEPOINT.
    """
    codes = {random_short_code(7) for _ in range(batch)}
    if not codes:
        return 0
    await redis.sadd(POOL_KEY, *codes)
    return len(codes)
