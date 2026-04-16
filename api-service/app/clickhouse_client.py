"""Async ClickHouse client (clickhouse-connect)."""
from __future__ import annotations

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from app.config import settings

_client: AsyncClient | None = None


async def init_clickhouse() -> None:
    """Idempotently create a ClickHouse async client."""
    global _client
    if _client is not None:
        return
    _client = await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password.get_secret_value(),
        database=settings.clickhouse_db,
        connect_timeout=5,
        query_limit=100_000,
    )


async def close_clickhouse() -> None:
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:  # noqa: BLE001 - don't crash shutdown
            pass
        _client = None


def get_clickhouse() -> AsyncClient:
    if _client is None:
        raise RuntimeError("ClickHouse client is not initialised")
    return _client
