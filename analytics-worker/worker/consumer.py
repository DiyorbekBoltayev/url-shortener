"""XREADGROUP consumer loop + group-ensure helper."""
from __future__ import annotations

import asyncio
import os
import socket
from typing import Any

from redis.exceptions import ResponseError

from .enricher import Enricher
from .logging import get_logger
from .metrics import EVENTS_CONSUMED, EVENTS_DROPPED, EVENTS_ENRICHED
from .writer import ClickHouseBatchWriter

log = get_logger(__name__)


def build_consumer_id() -> str:
    host = os.getenv("HOSTNAME") or socket.gethostname() or "worker"
    return f"{host}-{os.getpid()}"


async def ensure_group(redis_client: Any, stream: str, group: str) -> None:
    """Idempotently create the consumer group. Swallow BUSYGROUP."""
    try:
        await redis_client.xgroup_create(
            name=stream, groupname=group, id="$", mkstream=True
        )
        log.info("group_created", stream=stream, group=group)
    except ResponseError as e:
        if "BUSYGROUP" in str(e):
            log.debug("group_exists", stream=stream, group=group)
            return
        raise


async def ticker(
    writer: ClickHouseBatchWriter,
    stop: asyncio.Event,
    interval: float,
) -> None:
    """Time-based flush trigger. Runs in its own task."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return  # stop set -> exit
        except asyncio.TimeoutError:
            pass
        try:
            await writer.flush_if_due()
        except Exception:
            log.exception("ticker_flush_failed")


async def run_consumer(
    redis_client: Any,
    enricher: Enricher,
    writer: ClickHouseBatchWriter,
    *,
    stream: str,
    group: str,
    consumer_id: str,
    stop: asyncio.Event,
    count: int,
    block_ms: int,
) -> None:
    """Main XREADGROUP loop. Reads up to `count` entries per iteration, enriches
    each, and pushes into the writer's buffer. The writer's own size-trigger +
    ticker handle flushing.
    """
    log.info(
        "consumer_started",
        stream=stream,
        group=group,
        consumer=consumer_id,
        count=count,
        block_ms=block_ms,
    )
    while not stop.is_set():
        try:
            resp = await redis_client.xreadgroup(
                groupname=group,
                consumername=consumer_id,
                streams={stream: ">"},
                count=count,
                block=block_ms,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Auto-recover if the consumer group was lost (e.g. Redis wiped,
            # stream re-created). This loop would otherwise spam NOGROUP
            # forever until a human runs XGROUP CREATE.
            if "NOGROUP" in str(exc):
                try:
                    await redis_client.xgroup_create(
                        stream, group, id="0", mkstream=True
                    )
                    log.warning("consumer_group_recreated", stream=stream, group=group)
                except Exception:  # BUSYGROUP is fine; any other error we log
                    log.exception("consumer_group_recreate_failed")
            else:
                log.exception("xreadgroup_failed")
            await asyncio.sleep(1.0)
            continue

        if not resp:
            # Idle tick; let the ticker flush anything pending.
            continue

        for _stream_name, entries in resp:
            for msg_id, fields in entries:
                EVENTS_CONSUMED.inc()
                try:
                    row = enricher.enrich(fields)
                except Exception:
                    EVENTS_DROPPED.labels(reason="enrich_error").inc()
                    log.exception("enrich_failed", msg_id=msg_id)
                    # Ack poisonous payloads so they don't recycle forever.
                    try:
                        await redis_client.xack(stream, group, msg_id)
                    except Exception:
                        log.exception("xack_poison_failed", msg_id=msg_id)
                    continue
                EVENTS_ENRICHED.inc()
                await writer.add(msg_id, row.as_tuple())

    log.info("consumer_stopping", consumer=consumer_id)
