"""Smoke tests for /health and /ready."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ready(client):
    r = await client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_health_returns_json(client):
    r = await client.get("/health")
    # ClickHouse is not initialised in tests -> 503 is fine, but the shape
    # must be valid and the critical redis/postgres checks must exist.
    body = r.json()
    assert "checks" in body
    assert "postgres" in body["checks"]
    assert "redis" in body["checks"]
