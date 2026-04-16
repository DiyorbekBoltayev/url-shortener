"""Shared pytest fixtures for worker tests.

Uses fakeredis (supports XREADGROUP/XACK/XPENDING/XCLAIM) and a mock CH client.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeredis


@pytest_asyncio.fixture
async def redis_client():
    r = fakeredis.FakeRedis(decode_responses=False)
    yield r
    try:
        await r.aclose()
    except Exception:
        pass


@pytest.fixture
def ch_mock():
    m = AsyncMock()
    m.insert = AsyncMock(return_value=None)
    m.close = AsyncMock(return_value=None)
    return m


@pytest.fixture
def stream_name() -> str:
    return "stream:clicks"


@pytest.fixture
def group_name() -> str:
    return "analytics"


@pytest_asyncio.fixture
async def group_ready(redis_client, stream_name, group_name):
    """Create stream + consumer group (MKSTREAM)."""
    try:
        await redis_client.xgroup_create(
            name=stream_name, groupname=group_name, id="$", mkstream=True
        )
    except Exception:
        pass
    return redis_client


@pytest.fixture
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()
