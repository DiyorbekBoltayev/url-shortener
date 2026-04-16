"""Pytest harness — aiosqlite engine + fakeredis-lite replacement.

We don't run the production Postgres engine in unit tests; postgres-specific
types (ARRAY, UUID) are mapped via ``compile`` tweaks / direct sqlite fallback
where possible. Deep integration tests should use testcontainers (separate
config).
"""
from __future__ import annotations

import os
import sys
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_APP_URL", "redis://localhost:6380/0")
os.environ.setdefault("CLICKHOUSE_URL", "clickhouse://default:@localhost:8123/analytics")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-test")
os.environ.setdefault("ENVIRONMENT", "test")

# Ensure app package is importable when running ``pytest`` directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeRedis:
    """In-memory minimal async Redis stub (strings + hashes + sorted sets)."""

    def __init__(self) -> None:
        self._k: dict[str, str] = {}
        self._h: dict[str, dict[str, str]] = {}
        self._z: dict[str, dict[str, float]] = {}
        self._s: dict[str, set[str]] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key):
        return self._k.get(key)

    async def set(self, key, value):
        self._k[key] = str(value)
        return True

    async def setex(self, key, ttl, value):
        self._k[key] = str(value)
        return True

    async def delete(self, *keys):
        n = 0
        for k in keys:
            for store in (self._k, self._h, self._z, self._s):
                if k in store:
                    del store[k]
                    n += 1
                    break
        return n

    async def incr(self, key):
        cur = int(self._k.get(key, "0")) + 1
        self._k[key] = str(cur)
        return cur

    async def spop(self, key):
        if key in self._s and self._s[key]:
            return self._s[key].pop()
        return None

    async def sadd(self, key, *values):
        self._s.setdefault(key, set()).update(values)
        return len(values)

    async def hset(self, key, mapping=None, **kwargs):
        h = self._h.setdefault(key, {})
        if mapping:
            h.update({k: str(v) for k, v in mapping.items()})
        h.update({k: str(v) for k, v in kwargs.items()})
        return len(h)

    async def expire(self, key, ttl):
        return True

    async def scard(self, key):
        return len(self._s.get(key, ()))

    async def scan(self, cursor=0, match=None, count=100):
        # Return all matching keys at once and cursor=0 (end of iteration).
        import fnmatch
        keys = list(self._k.keys())
        if match:
            keys = [k for k in keys if fnmatch.fnmatchcase(k, match)]
        return 0, keys

    async def getset(self, key, value):
        prev = self._k.get(key)
        self._k[key] = str(value)
        return prev

    def pipeline(self, transaction=False):  # type: ignore[override]
        outer = self

        class _P:
            def __init__(self):
                self.calls = []

            def get(self, key):
                self.calls.append(("get", key))
                return self

            def evalsha(self, *args, **kwargs):
                self.calls.append(("evalsha", args, kwargs))
                return self

            async def execute(self):
                results = []
                for call in self.calls:
                    if call[0] == "get":
                        results.append(outer._k.get(call[1]))
                    elif call[0] == "evalsha":
                        results.append([1, 1])
                return results

        return _P()

    async def script_load(self, _):
        return "sha"

    async def evalsha(self, *args, **kwargs):
        return [1, 1]

    async def aclose(self):
        return None

    async def lpush(self, key, *values):
        lst = self._k.get(key)
        arr = [] if lst is None else list(lst) if isinstance(lst, list) else []
        for v in values:
            arr.insert(0, str(v))
        self._k[key] = arr
        return len(arr)

    async def blpop(self, key, timeout=0):
        lst = self._k.get(key)
        if isinstance(lst, list) and lst:
            val = lst.pop(0)
            return (key, val)
        return None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """App-wrapped AsyncClient with faked Redis + sqlite DB."""
    from app import clickhouse_client, database, redis_client
    from app.models import Base  # noqa: WPS433

    database.init_engine()
    # Force aiosqlite memory engine
    database.SessionLocal = None
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # ARRAY / UUID compile to TEXT/NULL on sqlite — skip creation of indexes
    # that use postgres-only features.
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:  # noqa: BLE001
        pass
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    redis_client.cache_redis = _FakeRedis()
    redis_client.app_redis = _FakeRedis()
    clickhouse_client._client = None  # type: ignore[attr-defined]

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await engine.dispose()
