"""Periodic Pending Entries List reclaimer.

Every `interval_sec` seconds:
  1. XAUTOCLAIM (Redis 6.2+) from cursor for entries idle >= idle_ms.
     Fallback to XPENDING + XCLAIM if the server doesn't support XAUTOCLAIM.
  2. For each reclaimed entry, enrich + add to writer buffer (same path as
     a fresh XREADGROUP entry; the writer's normal flush/XACK path finishes it).
  3. After `max_deliveries` attempts on the same ID, route to a dead-letter
     stream (`<stream>:dead`) and XACK the original to stop recycling.

Also samples `queue_lag_ms` from XPENDING.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from redis.exceptions import ResponseError

from .enricher import Enricher
from .logging import get_logger
from .metrics import (
    EVENTS_DROPPED,
    EVENTS_ENRICHED,
    EVENTS_RECLAIMED,
    QUEUE_LAG_MS,
)
from .writer import ClickHouseBatchWriter

log = get_logger(__name__)


def _entry_ts_ms(msg_id: bytes | str) -> int:
    """Extract the Redis-XID timestamp (ms) from 'ms-seq'."""
    s = msg_id.decode("ascii", "replace") if isinstance(msg_id, bytes) else msg_id
    try:
        return int(s.split("-", 1)[0])
    except (ValueError, IndexError):
        return 0


async def _sample_lag(redis_client: Any, stream: str, group: str) -> None:
    try:
        info = await redis_client.xpending(stream, group)
    except Exception:
        return
    # redis-py returns a dict for the summary form.
    pending = 0
    min_id: bytes | str | None = None
    if isinstance(info, dict):
        pending = int(info.get("pending") or 0)
        min_id = info.get("min")
    elif isinstance(info, (list, tuple)) and len(info) >= 2:
        pending = int(info[0] or 0)
        min_id = info[1]
    if pending and min_id:
        ms = _entry_ts_ms(min_id)
        if ms:
            QUEUE_LAG_MS.set(max(0.0, time.time() * 1000.0 - ms))
            return
    QUEUE_LAG_MS.set(0.0)


async def _autoclaim_batch(
    redis_client: Any,
    stream: str,
    group: str,
    consumer: str,
    idle_ms: int,
    cursor: str,
    count: int,
) -> tuple[str, list[tuple[bytes, dict]], bool]:
    """Returns (next_cursor, claimed, used_fallback)."""
    try:
        res = await redis_client.xautoclaim(
            name=stream,
            groupname=group,
            consumername=consumer,
            min_idle_time=idle_ms,
            start_id=cursor,
            count=count,
        )
    except (ResponseError, AttributeError):
        return await _xpending_claim_fallback(
            redis_client, stream, group, consumer, idle_ms, count
        ) + (True,)  # type: ignore[return-value]
    # redis-py shape: (next_cursor, claimed_entries, deleted_ids)
    if isinstance(res, (list, tuple)) and len(res) >= 2:
        next_cursor_raw, claimed = res[0], res[1]
    else:
        return "0-0", [], False
    next_cursor = (
        next_cursor_raw.decode()
        if isinstance(next_cursor_raw, bytes)
        else str(next_cursor_raw)
    )
    return next_cursor, list(claimed), False


async def _xpending_claim_fallback(
    redis_client: Any,
    stream: str,
    group: str,
    consumer: str,
    idle_ms: int,
    count: int,
) -> tuple[str, list[tuple[bytes, dict]]]:
    pending = await redis_client.xpending_range(
        name=stream,
        groupname=group,
        min="-",
        max="+",
        count=count,
        idle=idle_ms,
    )
    if not pending:
        return "0-0", []
    ids = [p["message_id"] for p in pending]
    claimed = await redis_client.xclaim(
        name=stream,
        groupname=group,
        consumername=consumer,
        min_idle_time=idle_ms,
        message_ids=ids,
    )
    return "0-0", list(claimed)


async def _handle_poison(
    redis_client: Any,
    stream: str,
    group: str,
    msg_id: bytes,
    fields: dict,
    max_deliveries: int,
) -> bool:
    """If this entry has been delivered > max_deliveries times, route to DLQ
    and XACK the original. Returns True if the entry was consumed (don't process)."""
    try:
        details = await redis_client.xpending_range(
            name=stream, groupname=group, min=msg_id, max=msg_id, count=1
        )
    except Exception:
        return False
    if not details:
        return False
    info = details[0]
    # redis-py returns dict with 'times_delivered' key
    times = int(info.get("times_delivered") or info.get("deliveries") or 0)
    if times <= max_deliveries:
        return False
    dlq = f"{stream}:dead"
    try:
        flat: list[bytes] = []
        for k, v in fields.items():
            flat.append(k if isinstance(k, bytes) else str(k).encode())
            flat.append(v if isinstance(v, bytes) else str(v).encode())
        payload = dict(zip(flat[0::2], flat[1::2], strict=True))
        # Include original id & delivery count for forensics.
        payload[b"_orig_id"] = msg_id
        payload[b"_times_delivered"] = str(times).encode()
        await redis_client.xadd(dlq, payload, maxlen=100_000, approximate=True)
        await redis_client.xack(stream, group, msg_id)
        EVENTS_DROPPED.labels(reason="dead_letter").inc()
        log.warning("dead_lettered", msg_id=msg_id, times=times, dlq=dlq)
        return True
    except Exception:
        log.exception("dead_letter_failed", msg_id=msg_id)
        return False


async def run_pel_reclaimer(
    redis_client: Any,
    enricher: Enricher,
    writer: ClickHouseBatchWriter,
    *,
    stream: str,
    group: str,
    consumer_id: str,
    stop: asyncio.Event,
    idle_ms: int,
    interval_sec: float,
    max_deliveries: int,
) -> None:
    log.info(
        "pel_reclaimer_started",
        stream=stream,
        group=group,
        consumer=consumer_id,
        idle_ms=idle_ms,
        interval_sec=interval_sec,
    )
    cursor = "0-0"
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_sec)
            break  # stop set
        except asyncio.TimeoutError:
            pass

        await _sample_lag(redis_client, stream, group)

        try:
            cursor, claimed, _used_fallback = await _autoclaim_batch(
                redis_client,
                stream,
                group,
                consumer_id,
                idle_ms,
                cursor,
                count=100,
            )
        except Exception:
            log.exception("pel_reclaim_iteration_failed")
            cursor = "0-0"
            continue

        for msg_id, fields in claimed:
            # Dead-letter poisonous entries.
            if await _handle_poison(
                redis_client, stream, group, msg_id, fields, max_deliveries
            ):
                continue
            EVENTS_RECLAIMED.inc()
            try:
                row = enricher.enrich(fields)
            except Exception:
                EVENTS_DROPPED.labels(reason="enrich_error").inc()
                log.exception("reclaim_enrich_failed", msg_id=msg_id)
                try:
                    await redis_client.xack(stream, group, msg_id)
                except Exception:
                    log.exception("reclaim_xack_poison_failed", msg_id=msg_id)
                continue
            EVENTS_ENRICHED.inc()
            await writer.add(msg_id, row.as_tuple())

    log.info("pel_reclaimer_stopping")
