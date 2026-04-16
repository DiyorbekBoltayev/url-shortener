"""analytics-worker entrypoint.

Wires Redis + ClickHouse + GeoIP + enricher + writer + consumer + PEL reclaimer.
Handles SIGTERM/SIGINT (Unix); on Windows we fall back to KeyboardInterrupt
because `loop.add_signal_handler` is not supported there.
"""
from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

import clickhouse_connect
import redis.asyncio as aioredis

from .config import Settings, load_settings
from .consumer import build_consumer_id, ensure_group, run_consumer, ticker
from .enricher import Enricher
from .geoip import GeoIPReader
from .health import start_health_server, stop_health_server
from .logging import configure_logging, get_logger
from .metrics import start_metrics_server
from .pel_reclaimer import run_pel_reclaimer
from .writer import ClickHouseBatchWriter

log = get_logger(__name__)


async def _build_ch_client(s: Settings) -> Any:
    """Create an async ClickHouse client (HTTP protocol on 8123)."""
    return await clickhouse_connect.get_async_client(
        host=s.clickhouse_host,
        port=s.clickhouse_http_port,
        username=s.clickhouse_user,
        password=s.clickhouse_password.get_secret_value(),
        database=s.clickhouse_db,
        compress="lz4",
    )


def _install_signal_handlers(stop: asyncio.Event) -> None:
    """SIGTERM/SIGINT -> stop.set(). On Windows asyncio doesn't support
    add_signal_handler, so we rely on KeyboardInterrupt instead."""
    loop = asyncio.get_running_loop()
    if sys.platform == "win32":
        log.debug("signal_handlers_skipped_windows")
        return
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass


async def run() -> None:
    s = load_settings()
    configure_logging(s.log_level)
    log.info(
        "boot",
        stream=s.stream_name,
        group=s.consumer_group,
        batch_size=s.batch_size,
        flush_interval_sec=s.flush_interval_sec,
    )

    # Metrics HTTP server (blocking start, doesn't return the server obj).
    start_metrics_server(s.metrics_port)

    # External deps
    redis_client = aioredis.from_url(
        s.redis_stream_url,
        decode_responses=False,  # stream payloads carry raw bytes
    )
    ch_client = await _build_ch_client(s)

    geo = GeoIPReader(s.geoip_db_path)
    enricher = Enricher(geo)
    writer = ClickHouseBatchWriter(
        ch_client,
        redis_client,
        stream=s.stream_name,
        group=s.consumer_group,
        batch_size=s.batch_size,
        flush_interval=s.flush_interval_sec,
    )

    await ensure_group(redis_client, s.stream_name, s.consumer_group)

    stop = asyncio.Event()
    _install_signal_handlers(stop)

    consumer_id = build_consumer_id()

    # Health server
    health_runner, _ = await start_health_server(s.health_port)

    tasks: list[asyncio.Task] = [
        asyncio.create_task(
            run_consumer(
                redis_client,
                enricher,
                writer,
                stream=s.stream_name,
                group=s.consumer_group,
                consumer_id=consumer_id,
                stop=stop,
                count=s.read_count,
                block_ms=s.read_block_ms,
            ),
            name="consumer",
        ),
        asyncio.create_task(
            ticker(writer, stop, s.flush_interval_sec),
            name="writer-ticker",
        ),
        asyncio.create_task(
            run_pel_reclaimer(
                redis_client,
                enricher,
                writer,
                stream=s.stream_name,
                group=s.consumer_group,
                consumer_id=consumer_id,
                stop=stop,
                idle_ms=s.pel_idle_ms,
                interval_sec=s.pel_claim_interval_sec,
                max_deliveries=s.pel_max_deliveries,
            ),
            name="pel-reclaimer",
        ),
    ]

    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        stop.set()
    finally:
        log.info("shutdown_begin")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # Drain whatever is buffered.
        try:
            await writer.drain()
        except Exception:
            log.exception("drain_failed")

        # Close external clients.
        await stop_health_server(health_runner)
        try:
            await redis_client.aclose()
        except Exception:
            log.exception("redis_close_failed")
        try:
            await ch_client.close()
        except Exception:
            log.exception("ch_close_failed")
        geo.close()

        log.info("shutdown_complete")


def run_cli() -> None:
    """Console-script entrypoint."""
    # Prefer uvloop on non-Windows platforms for ~20% throughput uplift.
    if sys.platform != "win32":
        try:
            import uvloop  # type: ignore[import-not-found]

            uvloop.install()
        except ImportError:
            pass
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_cli()
