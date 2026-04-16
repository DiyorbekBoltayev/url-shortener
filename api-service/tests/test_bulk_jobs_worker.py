"""Bulk import worker — S4 smoke test.

Runs the CSV import handler end-to-end against the in-memory SQLite DB
fixture. MinIO / export path is skipped here — covered separately, would
need ``minio`` installed.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database, redis_client
from app.models import Base, BulkJob
from app.models.url import Url
from app.services import bulk_jobs_service
from tests.conftest import _FakeRedis


async def _fresh_env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:  # noqa: BLE001 — PG-only indexes on sqlite
            pass
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    database.engine = engine
    database.SessionLocal = session_factory
    redis_client.cache_redis = _FakeRedis()
    redis_client.app_redis = _FakeRedis()

    # Force safety scan to resolve as "ok" immediately so the synchronous
    # 500ms budget never triggers.
    from app.services import safety_service

    async def _fast_ok(_url, *, cache=None):
        return safety_service.SafetyVerdict(status="ok")

    monkeypatch.setattr(safety_service, "scan", _fast_ok)
    return engine, session_factory


@pytest.mark.asyncio
async def test_import_three_rows_all_succeed(monkeypatch):
    engine, session_factory = await _fresh_env(monkeypatch)
    csv_text = (
        "long_url,title\n"
        "https://example.com/a,Alpha\n"
        "https://example.com/b,Bravo\n"
        "https://example.com/c,Charlie\n"
    )
    async with session_factory() as db:
        job = BulkJob(
            kind="import",
            status="pending",
            params={"csv_text": csv_text},
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    await bulk_jobs_service.process_one(
        session_factory,
        redis_client.cache_redis,
        redis_client.app_redis,
        job_id,
    )

    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        assert job is not None
        assert job.status == "done", job.error_message
        assert job.total == 3
        assert job.done == 3
        assert job.failed == 0

        url_rows = (await db.execute(select(Url))).scalars().all()
        assert len(url_rows) == 3
        assert {r.title for r in url_rows} == {"Alpha", "Bravo", "Charlie"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_import_bad_row_counts_as_failed(monkeypatch):
    engine, session_factory = await _fresh_env(monkeypatch)
    csv_text = "long_url\nhttps://example.com/ok\nnot-a-url\n"
    async with session_factory() as db:
        job = BulkJob(
            kind="import",
            status="pending",
            params={"csv_text": csv_text},
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    await bulk_jobs_service.process_one(
        session_factory,
        redis_client.cache_redis,
        redis_client.app_redis,
        job_id,
    )

    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        assert job is not None
        assert job.status == "done"
        assert job.total == 2
        assert job.done == 1
        assert job.failed == 1

    await engine.dispose()
