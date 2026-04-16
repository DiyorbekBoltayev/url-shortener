"""Buffered batch writer: ClickHouse INSERT + XACK after durable write.

Flush triggers:
  - buffer size >= batch_size
  - time since last flush >= flush_interval (size=0 means noop)
  - explicit drain on shutdown

Retry with tenacity; on final failure we DO NOT XACK — the entries stay in
the consumer-group PEL, and PEL reclaimer / restart will replay them.
ReplacingMergeTree dedupes by `stream_id` (see schema in research doc).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .logging import get_logger
from .metrics import (
    BATCH_SIZE,
    CLICKHOUSE_INSERT_ERRORS,
    EVENTS_FLUSHED,
    FLUSH_DURATION,
    LAST_FLUSH_TS,
)

log = get_logger(__name__)

COLS: tuple[str, ...] = (
    "clicked_at",
    "short_code",
    "ip_hash",
    "country_code",
    "country_name",
    "region",
    "city",
    "latitude",
    "longitude",
    "device_type",
    "browser",
    "browser_version",
    "os",
    "os_version",
    "is_bot",
    "bot_name",
    "referer_url",
    "referer_domain",
    "referer_type",
    "utm_source",
    "utm_medium",
    "utm_campaign",
)


@dataclass(slots=True)
class Row:
    """(msg_id, values) pair — values ordered per COLS minus stream_id."""

    msg_id: bytes
    values: tuple


class ClickHouseBatchWriter:
    """Owns the buffer and the flush. The consumer calls `add()`; the time-
    ticker + size-trigger call `flush()`. On insert failure, entries remain
    in Redis PEL (no XACK).
    """

    def __init__(
        self,
        ch_client: Any,
        redis_client: Any,
        *,
        table: str = "clicks",
        stream: str = "stream:clicks",
        group: str = "analytics",
        batch_size: int = 1000,
        flush_interval: float = 1.0,
    ) -> None:
        self._ch = ch_client
        self._redis = redis_client
        self._table = table
        self._stream = stream
        self._group = group
        self._batch_size = batch_size
        self._interval = flush_interval
        self._buffer: list[Row] = []
        self._lock = asyncio.Lock()
        self._last_flush = time.monotonic()

    def __len__(self) -> int:
        return len(self._buffer)

    async def add(self, msg_id: bytes, values: tuple) -> bool:
        """Append a row. Returns True if a size-triggered flush ran."""
        async with self._lock:
            self._buffer.append(Row(msg_id=msg_id, values=values))
            if len(self._buffer) >= self._batch_size:
                await self._flush_locked()
                return True
        return False

    async def flush_if_due(self) -> bool:
        """Time-based trigger; caller (ticker) invokes periodically."""
        async with self._lock:
            if not self._buffer:
                self._last_flush = time.monotonic()
                return False
            if (time.monotonic() - self._last_flush) >= self._interval:
                await self._flush_locked()
                return True
        return False

    async def drain(self) -> None:
        """Shutdown path: one last flush if anything is buffered."""
        async with self._lock:
            if self._buffer:
                await self._flush_locked()

    async def _flush_locked(self) -> list[bytes]:
        """Caller must hold self._lock. Returns the XACKed msg-ids (or [] on failure)."""
        if not self._buffer:
            return []
        rows = self._buffer
        self._buffer = []
        msg_ids = [r.msg_id for r in rows]
        values = [r.values for r in rows]
        n = len(rows)
        t0 = time.monotonic()
        try:
            await self._insert_with_retry(values)
        except Exception:  # noqa: BLE001
            CLICKHOUSE_INSERT_ERRORS.inc()
            log.exception("ch_insert_final_failure", rows=n)
            # Return buffer so a subsequent drain/flush could see nothing new;
            # entries will be reclaimed via PEL because XACK did not run.
            self._last_flush = time.monotonic()
            return []
        # XACK only after durable insert.
        try:
            await self._redis.xack(self._stream, self._group, *msg_ids)
        except Exception:
            log.exception("xack_failed", rows=n)
            # Data is in CH but XACK failed; ReplacingMergeTree dedupes on replay.
        elapsed = time.monotonic() - t0
        BATCH_SIZE.observe(n)
        FLUSH_DURATION.observe(elapsed)
        EVENTS_FLUSHED.inc(n)
        LAST_FLUSH_TS.set(time.time())
        self._last_flush = time.monotonic()
        log.info("flush_ok", rows=n, elapsed_s=round(elapsed, 4))
        return msg_ids

    async def _insert_with_retry(self, values: list[tuple]) -> None:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential_jitter(initial=0.2, max=5.0),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(log, 30),
            reraise=True,
        ):
            with attempt:
                await self._ch.insert(
                    self._table,
                    values,
                    column_names=COLS,
                )
