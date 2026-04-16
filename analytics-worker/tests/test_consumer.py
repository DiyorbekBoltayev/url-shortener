"""Consumer + ensure_group tests — fakeredis."""
from __future__ import annotations

import asyncio

import pytest

from worker.consumer import build_consumer_id, ensure_group, run_consumer
from worker.enricher import Enricher
from worker.geoip import Geo, GeoIPReader
from worker.writer import ClickHouseBatchWriter


class _StubGeo(GeoIPReader):
    def __init__(self):
        self._reader = None
        self._path = ""

    def lookup(self, ip: str) -> Geo:  # type: ignore[override]
        return Geo(None, None, None, None, None, None)

    def close(self) -> None:
        pass


def test_consumer_id_format():
    cid = build_consumer_id()
    assert "-" in cid
    assert cid.split("-")[-1].isdigit()  # pid suffix


@pytest.mark.asyncio
async def test_ensure_group_idempotent(redis_client, stream_name, group_name):
    await ensure_group(redis_client, stream_name, group_name)
    # second call must not raise (BUSYGROUP swallowed)
    await ensure_group(redis_client, stream_name, group_name)


@pytest.mark.asyncio
async def test_consumer_reads_and_buffers(redis_client, ch_mock, stream_name, group_name):
    await ensure_group(redis_client, stream_name, group_name)
    # Pre-publish 2 clicks.
    for code in (b"aaa", b"bbb"):
        await redis_client.xadd(
            stream_name,
            {
                b"code": code,
                b"ts": b"1728345600000",
                b"ip": b"1.1.1.1",
                b"ua": b"Mozilla/5.0 Chrome/120",
                b"ref": b"",
                b"country": b"US",
            },
        )
    writer = ClickHouseBatchWriter(
        ch_mock,
        redis_client,
        stream=stream_name,
        group=group_name,
        batch_size=2,
        flush_interval=60.0,
    )
    enricher = Enricher(_StubGeo())
    stop = asyncio.Event()

    async def stopper():
        # wait for an insert then stop
        for _ in range(50):
            if ch_mock.insert.await_count >= 1:
                break
            await asyncio.sleep(0.05)
        stop.set()

    task = asyncio.create_task(
        run_consumer(
            redis_client,
            enricher,
            writer,
            stream=stream_name,
            group=group_name,
            consumer_id="test-consumer",
            stop=stop,
            count=10,
            block_ms=100,
        )
    )
    stopper_task = asyncio.create_task(stopper())
    await asyncio.wait_for(asyncio.gather(task, stopper_task), timeout=5.0)
    assert ch_mock.insert.await_count == 1
    assert len(ch_mock.insert.await_args.args[1]) == 2
