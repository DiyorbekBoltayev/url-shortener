"""Bulk job processors — import / export / bulk_patch.

Dispatched by the background loop in :mod:`app.main`. S1 owns the
``bulk_jobs`` table + router; the router LPUSHes the job id on
``bulk:jobs:pending`` and we BLPOP it here.

Shape of ``BulkJob.params`` per kind (see FEATURES_PLAN):

* ``import``      — ``{"csv_text": "<raw>", "column_map": {...}, "default_tag": ..., "default_folder_id": ...}``
  The v1 route stores the raw CSV (< 1 MB) inline; a future revision may
  upload to MinIO and pass ``{"csv_url": ...}`` instead. Both are
  supported here — ``csv_url`` wins when present.
* ``export``      — ``{"filter": {...}, "format": "csv"}``
* ``bulk_patch``  — ``{"ids": [...], "patch": {...}}``
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import minio_client
from app.config import settings
from app.logging import get_logger
from app.models.bulk_job import BulkJob
from app.models.url import Url
from app.schemas.url import URLCreate
from app.services import url_service

log = get_logger(__name__)

BULK_JOB_QUEUE = "bulk:jobs:pending"
# v1 hard limit — any bigger and the JSONB blob becomes unwieldy. The
# API router is expected to reject larger uploads before enqueueing.
_MAX_IMPORT_CSV_BYTES = 1_048_576  # 1 MB


# ----- Entry point --------------------------------------------------------


async def process_one(
    session_factory: async_sessionmaker[AsyncSession],
    cache_redis: Redis,
    app_redis: Redis,
    job_id: UUID,
) -> None:
    """Run job ``job_id`` end-to-end. Errors are swallowed + logged so
    the caller loop never crashes."""
    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is None:
            log.warning("bulk_job_missing", job_id=str(job_id))
            return
        if job.status in {"done", "failed"}:
            # Already processed — another worker picked it up.
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    try:
        if job.kind == "import":
            await _run_import(session_factory, cache_redis, app_redis, job_id)
        elif job.kind == "export":
            await _run_export(session_factory, job_id)
        elif job.kind == "bulk_patch":
            await _run_bulk_patch(session_factory, cache_redis, job_id)
        else:
            await _finish(
                session_factory,
                job_id,
                status="failed",
                error=f"unknown kind: {job.kind}",
            )
            return
    except Exception as exc:  # noqa: BLE001
        log.exception("bulk_job_failed", job_id=str(job_id), err=str(exc))
        await _finish(
            session_factory, job_id, status="failed", error=str(exc)[:500]
        )


# ----- Helpers ------------------------------------------------------------


async def _finish(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    *,
    status: str,
    error: str | None = None,
    result_url: str | None = None,
) -> None:
    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is None:
            return
        job.status = status
        job.finished_at = datetime.now(timezone.utc)
        if error is not None:
            job.error_message = error
        if result_url is not None:
            job.result_url = result_url
        await db.commit()


# ----- Import -------------------------------------------------------------


async def _load_csv_text(params: dict[str, Any]) -> str:
    """Retrieve the raw CSV to import.

    Two shapes supported: inline ``csv_text`` (v1 default) and
    ``csv_url`` pointing at a MinIO-presigned GET (planned for v2, safe
    from SSRF because our own MinIO is internal but we still route
    through :mod:`app.utils.safe_http` when the URL looks public).
    """
    csv_text = params.get("csv_text")
    if isinstance(csv_text, str):
        if len(csv_text.encode("utf-8")) > _MAX_IMPORT_CSV_BYTES:
            raise ValueError("csv_text exceeds 1MB limit")
        return csv_text
    # v2 path — not exercised yet; leaves a breadcrumb for future use.
    raise ValueError("bulk import params missing 'csv_text'")


async def _run_import(
    session_factory: async_sessionmaker[AsyncSession],
    cache_redis: Redis,
    app_redis: Redis,
    job_id: UUID,
) -> None:
    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is None:
            return
        params = dict(job.params or {})
        workspace_id = job.workspace_id
        user_id = job.user_id

    csv_text = await _load_csv_text(params)
    column_map = dict(params.get("column_map") or {})
    default_tag = params.get("default_tag")
    default_folder_id = params.get("default_folder_id")

    reader = csv.DictReader(io.StringIO(csv_text))

    def _col(row: dict[str, str], logical: str) -> str | None:
        physical = column_map.get(logical, logical)
        val = row.get(physical)
        return val.strip() if isinstance(val, str) and val.strip() else None

    rows = list(reader)
    total = len(rows)
    done = 0
    failed = 0

    # Flush counters in batches to avoid N+1 commits.
    BATCH = 50
    async with session_factory() as db:
        for idx, raw in enumerate(rows):
            long_url = _col(raw, "long_url")
            if not long_url:
                failed += 1
                continue
            tags = []
            tag_val = _col(raw, "tag")
            if tag_val:
                tags.append(tag_val)
            if default_tag and default_tag not in tags:
                tags.append(default_tag)

            folder_id_raw = _col(raw, "folder_id") or default_folder_id
            try:
                folder_id = UUID(folder_id_raw) if folder_id_raw else None
            except (TypeError, ValueError):
                folder_id = None

            expires_raw = _col(raw, "expires_at")
            expires_at: datetime | None = None
            if expires_raw:
                try:
                    expires_at = datetime.fromisoformat(
                        expires_raw.replace("Z", "+00:00")
                    )
                except ValueError:
                    expires_at = None

            body = URLCreate(
                long_url=long_url,
                title=_col(raw, "title"),
                custom_slug=_col(raw, "custom_slug"),
                tags=tags,
                folder_id=folder_id,
                expires_at=expires_at,
            )
            try:
                async with db.begin_nested():
                    await url_service.create_url(
                        db,
                        cache_redis,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        body=body,
                        app_redis=app_redis,
                    )
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.info(
                    "bulk_import_row_failed",
                    job_id=str(job_id),
                    idx=idx,
                    err=str(exc),
                )
                failed += 1

            if (idx + 1) % BATCH == 0:
                await db.commit()

        await db.commit()

    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is not None:
            job.total = total
            job.done = done
            job.failed = failed
            job.status = "done"
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()


# ----- Export -------------------------------------------------------------


_EXPORT_COLUMNS = (
    "id",
    "short_code",
    "long_url",
    "title",
    "tags",
    "folder_id",
    "is_active",
    "click_count",
    "created_at",
    "expires_at",
    "safety_status",
)


async def _run_export(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
) -> None:
    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is None:
            return
        params = dict(job.params or {})
        workspace_id = job.workspace_id

    filt = dict(params.get("filter") or {})

    stmt = select(Url)
    if workspace_id is not None:
        stmt = stmt.where(Url.workspace_id == workspace_id)
    folder_id = filt.get("folder_id")
    if folder_id:
        try:
            stmt = stmt.where(Url.folder_id == UUID(str(folder_id)))
        except (TypeError, ValueError):
            pass
    q = filt.get("q")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Url.short_code.ilike(like)) | (Url.long_url.ilike(like))
        )
    tags = filt.get("tags") or []
    # ``any`` in Postgres; skipped on sqlite-in-test (filter is optional).
    for t in tags:
        try:
            stmt = stmt.where(Url.tags.any(t))
        except Exception:  # noqa: BLE001 — array-ops not portable
            break

    async with session_factory() as db:
        rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_COLUMNS)
    for r in rows:
        writer.writerow(_row_to_csv(r))
    csv_bytes = buf.getvalue().encode("utf-8")

    key = f"exports/{workspace_id or 'anon'}/{job_id}.csv"
    bucket = settings.minio_bucket_exports
    uploaded = await minio_client.upload_bytes(
        bucket, key, csv_bytes, content_type="text/csv"
    )
    if not uploaded:
        await _finish(
            session_factory,
            job_id,
            status="failed",
            error="minio_upload_failed (is MinIO reachable?)",
        )
        return
    result_url = await minio_client.presign_get(bucket, key, expires=86_400)

    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is not None:
            job.total = len(rows)
            job.done = len(rows)
            job.failed = 0
            job.status = "done"
            job.result_url = result_url
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()


def _row_to_csv(url_row: Url) -> Iterable[Any]:
    return (
        str(url_row.id),
        url_row.short_code,
        url_row.long_url,
        url_row.title or "",
        ",".join(url_row.tags or []),
        str(url_row.folder_id) if url_row.folder_id else "",
        "1" if url_row.is_active else "0",
        url_row.click_count,
        url_row.created_at.isoformat() if url_row.created_at else "",
        url_row.expires_at.isoformat() if url_row.expires_at else "",
        url_row.safety_status,
    )


# ----- Bulk patch ---------------------------------------------------------


_PATCHABLE_FIELDS = frozenset({"tag", "folder_id", "is_active", "expires_at"})


async def _run_bulk_patch(
    session_factory: async_sessionmaker[AsyncSession],
    cache_redis: Redis,
    job_id: UUID,
) -> None:
    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is None:
            return
        params = dict(job.params or {})
        workspace_id = job.workspace_id

    ids_raw = params.get("ids") or []
    patch = dict(params.get("patch") or {})
    patch = {k: v for k, v in patch.items() if k in _PATCHABLE_FIELDS}

    url_ids: list[UUID] = []
    for i in ids_raw:
        try:
            url_ids.append(UUID(str(i)))
        except (TypeError, ValueError):
            continue
    if not url_ids:
        await _finish(session_factory, job_id, status="done")
        return

    # ``tag`` in the patch dict is a shortcut for "append this tag". The
    # full array-merge is expressed below.
    tag_to_add = patch.pop("tag", None)

    # Build update dict from the remaining fields.
    update_values: dict[str, Any] = {}
    if "folder_id" in patch and patch["folder_id"] is not None:
        try:
            update_values["folder_id"] = UUID(str(patch["folder_id"]))
        except (TypeError, ValueError):
            pass
    elif "folder_id" in patch and patch["folder_id"] is None:
        update_values["folder_id"] = None
    if "is_active" in patch:
        update_values["is_active"] = bool(patch["is_active"])
    if "expires_at" in patch:
        exp = patch["expires_at"]
        if isinstance(exp, str):
            try:
                exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            except ValueError:
                exp = None
        update_values["expires_at"] = exp

    short_codes: list[str] = []
    async with session_factory() as db:
        stmt = select(Url).where(Url.id.in_(url_ids))
        if workspace_id is not None:
            stmt = stmt.where(Url.workspace_id == workspace_id)
        rows = (await db.execute(stmt)).scalars().all()
        for row in rows:
            for field, value in update_values.items():
                setattr(row, field, value)
            if tag_to_add and tag_to_add not in (row.tags or []):
                row.tags = list(row.tags or []) + [tag_to_add]
            short_codes.append(row.short_code)
        await db.commit()

    # Invalidate redirect cache entries so the redirect-service sees
    # the patch without waiting for the TTL.
    for code in short_codes:
        try:
            await cache_redis.delete(
                f"url:{code}",
                f"url:meta:{code}",
                f"url:rules:{code}",
                f"url:pixels:{code}",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("bulk_patch_cache_invalidate_failed", code=code, err=str(exc))

    async with session_factory() as db:
        job = await db.scalar(select(BulkJob).where(BulkJob.id == job_id))
        if job is not None:
            job.total = len(url_ids)
            job.done = len(short_codes)
            job.failed = len(url_ids) - len(short_codes)
            job.status = "done"
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
