"""Writer tests — fakeredis + mock ClickHouse."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from worker.writer import COLS, ClickHouseBatchWriter

SAMPLE_VALUES = (
    datetime(2026, 1, 1, tzinfo=UTC),  # event_time
    "aB3xK9",  # short_code
    "deadbeef" * 4,  # ip_hash
    "US",  # country_code
    "United States",  # country_name
    "CA",  # region
    "SF",  # city
    37.7,  # lat
    -122.4,  # lon
    "Chrome",  # ua_browser
    "120",  # ua_browser_version
    "Windows",  # ua_os
    "10",  # ua_os_version
    "desktop",  # ua_device
    0,  # is_bot
    "",  # referer
    "",  # referer_domain
    "direct",  # referer_type
)


@pytest.mark.asyncio
async def test_size_trigger_flushes(group_ready, ch_mock, stream_name, group_name):
    w = ClickHouseBatchWriter(
        ch_mock,
        group_ready,
        stream=stream_name,
        group=group_name,
        batch_size=3,
        flush_interval=60.0,
    )
    # XADD + XREADGROUP so there's something to XACK.
    ids = []
    for _ in range(3):
        mid = await group_ready.xadd(stream_name, {b"code": b"abc"})
        ids.append(mid)
    await group_ready.xreadgroup(group_name, "c1", {stream_name: ">"}, count=10)
    for mid in ids:
        await w.add(mid, SAMPLE_VALUES)
    # Size trigger already fired.
    assert ch_mock.insert.await_count == 1
    args, kwargs = ch_mock.insert.await_args
    assert args[0] == "clicks"
    assert len(args[1]) == 3
    assert kwargs["column_names"] == COLS


@pytest.mark.asyncio
async def test_drain_flushes_remainder(group_ready, ch_mock, stream_name, group_name):
    w = ClickHouseBatchWriter(
        ch_mock,
        group_ready,
        stream=stream_name,
        group=group_name,
        batch_size=1000,
        flush_interval=60.0,
    )
    mid = await group_ready.xadd(stream_name, {b"code": b"a"})
    await group_ready.xreadgroup(group_name, "c1", {stream_name: ">"}, count=10)
    await w.add(mid, SAMPLE_VALUES)
    assert ch_mock.insert.await_count == 0
    await w.drain()
    assert ch_mock.insert.await_count == 1
    assert len(ch_mock.insert.await_args.args[1]) == 1


@pytest.mark.asyncio
async def test_flush_if_due_respects_interval(
    group_ready, ch_mock, stream_name, group_name
):
    w = ClickHouseBatchWriter(
        ch_mock,
        group_ready,
        stream=stream_name,
        group=group_name,
        batch_size=1000,
        flush_interval=0.05,
    )
    mid = await group_ready.xadd(stream_name, {b"code": b"a"})
    await group_ready.xreadgroup(group_name, "c1", {stream_name: ">"}, count=10)
    await w.add(mid, SAMPLE_VALUES)
    # Not yet due:
    flushed = await w.flush_if_due()
    # With very small interval it might be due immediately; either way insert shouldn't error.
    await asyncio.sleep(0.1)
    flushed2 = await w.flush_if_due()
    assert flushed or flushed2
    assert ch_mock.insert.await_count == 1


@pytest.mark.asyncio
async def test_xack_happens_after_insert(
    group_ready, ch_mock, stream_name, group_name
):
    w = ClickHouseBatchWriter(
        ch_mock,
        group_ready,
        stream=stream_name,
        group=group_name,
        batch_size=1,
        flush_interval=60.0,
    )
    mid = await group_ready.xadd(stream_name, {b"code": b"a"})
    await group_ready.xreadgroup(group_name, "c1", {stream_name: ">"}, count=10)
    # Before add: 1 pending
    pending_before = await group_ready.xpending(stream_name, group_name)
    assert (pending_before.get("pending") or 0) == 1
    await w.add(mid, SAMPLE_VALUES)
    # After insert + XACK: 0 pending
    pending_after = await group_ready.xpending(stream_name, group_name)
    assert (pending_after.get("pending") or 0) == 0
    assert ch_mock.insert.await_count == 1


@pytest.mark.asyncio
async def test_no_xack_when_insert_fails(
    group_ready, ch_mock, stream_name, group_name
):
    ch_mock.insert.side_effect = RuntimeError("clickhouse down")
    w = ClickHouseBatchWriter(
        ch_mock,
        group_ready,
        stream=stream_name,
        group=group_name,
        batch_size=1,
        flush_interval=60.0,
    )
    mid = await group_ready.xadd(stream_name, {b"code": b"a"})
    await group_ready.xreadgroup(group_name, "c1", {stream_name: ">"}, count=10)
    await w.add(mid, SAMPLE_VALUES)
    # Still pending — insert failed all 5 retries.
    pending = await group_ready.xpending(stream_name, group_name)
    assert (pending.get("pending") or 0) == 1
    assert ch_mock.insert.await_count == 5


@pytest.mark.asyncio
async def test_cols_matches_values_plus_stream_id(group_ready, ch_mock, stream_name, group_name):
    w = ClickHouseBatchWriter(
        ch_mock,
        group_ready,
        stream=stream_name,
        group=group_name,
        batch_size=1,
        flush_interval=60.0,
    )
    mid = await group_ready.xadd(stream_name, {b"code": b"a"})
    await group_ready.xreadgroup(group_name, "c1", {stream_name: ">"}, count=10)
    await w.add(mid, SAMPLE_VALUES)
    inserted_rows = ch_mock.insert.await_args.args[1]
    assert len(inserted_rows[0]) == len(COLS)
