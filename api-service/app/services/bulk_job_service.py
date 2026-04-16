"""Bulk job service — enqueue into Redis + track progress via Postgres.

The actual workers (:mod:`app.services.bulk_jobs_service`) drain
``bulk:jobs:pending`` and update the rows they own. This module is
only concerned with enqueue / read access.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound
from app.models.bulk_job import BulkJob

BULK_JOB_QUEUE = "bulk:jobs:pending"


async def _enqueue(redis: Redis, job_id: UUID) -> None:
    # LPUSH — S4 workers BRPOP off the other end for FIFO semantics.
    await redis.lpush(BULK_JOB_QUEUE, str(job_id))


async def _persist(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    user_id: UUID | None,
    kind: str,
    params: dict[str, Any],
    total: int = 0,
) -> BulkJob:
    row = BulkJob(
        workspace_id=workspace_id,
        user_id=user_id,
        kind=kind,
        status="pending",
        total=total,
        done=0,
        failed=0,
        params=params,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def enqueue_import(
    db: AsyncSession,
    redis: Redis,
    *,
    workspace_id: UUID | None,
    user_id: UUID | None,
    csv_content: bytes,
    column_map: dict[str, str] | None,
    default_tag: str | None = None,
    default_folder_id: UUID | None = None,
) -> BulkJob:
    """Enqueue a CSV import job.

    The CSV text is stored inline in ``params.csv_text`` so the S4
    worker (:mod:`app.services.bulk_jobs_service`) can stream it
    without a second round trip. The router caps size before we get
    here.
    """
    # Rough line-count for total; subtract 1 for header row if present.
    try:
        total = max(0, csv_content.count(b"\n") - 1)
    except Exception:  # noqa: BLE001
        total = 0
    try:
        csv_text = csv_content.decode("utf-8")
    except UnicodeDecodeError:
        # Fall back to latin-1 so the worker can still parse non-UTF8
        # CSVs (Excel on Windows) without us having to guess.
        csv_text = csv_content.decode("latin-1")
    params: dict[str, Any] = {
        "csv_text": csv_text,
        "column_map": column_map or {},
    }
    if default_tag:
        params["default_tag"] = default_tag
    if default_folder_id:
        params["default_folder_id"] = str(default_folder_id)
    row = await _persist(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        kind="import",
        params=params,
        total=total,
    )
    await _enqueue(redis, row.id)
    return row


async def enqueue_export(
    db: AsyncSession,
    redis: Redis,
    *,
    workspace_id: UUID | None,
    user_id: UUID | None,
    filter_: dict[str, Any],
    fmt: str = "csv",
) -> BulkJob:
    row = await _persist(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        kind="export",
        params={"filter": filter_, "format": fmt},
    )
    await _enqueue(redis, row.id)
    return row


async def enqueue_bulk_patch(
    db: AsyncSession,
    redis: Redis,
    *,
    workspace_id: UUID | None,
    user_id: UUID | None,
    url_ids: list[UUID],
    patch: dict[str, Any],
) -> BulkJob:
    params = {
        "ids": [str(u) for u in url_ids],
        "patch": {k: (str(v) if isinstance(v, UUID) else v) for k, v in patch.items() if v is not None},
    }
    row = await _persist(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        kind="bulk_patch",
        params=params,
        total=len(url_ids),
    )
    await _enqueue(redis, row.id)
    return row


async def get(
    db: AsyncSession, *, workspace_id: UUID | None, job_id: UUID
) -> BulkJob:
    stmt = select(BulkJob).where(BulkJob.id == job_id)
    if workspace_id is not None:
        stmt = stmt.where(BulkJob.workspace_id == workspace_id)
    row = await db.scalar(stmt)
    if not row:
        raise NotFound("Bulk job not found")
    return row


async def list_recent(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    offset: int,
    limit: int,
) -> tuple[list[BulkJob], int]:
    base = select(BulkJob)
    if workspace_id is not None:
        base = base.where(BulkJob.workspace_id == workspace_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(BulkJob.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)
