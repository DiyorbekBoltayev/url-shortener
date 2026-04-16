"""Retarget pixel CRUD + attach/detach service."""
from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequest, NotFound
from app.models.retarget_pixel import RetargetPixel, link_pixels
from app.models.url import Url
from app.schemas.pixel import KIND_VALUES
from app.services import url_service


async def create(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    kind: str,
    pixel_id: str,
    name: str | None = None,
    is_active: bool = True,
) -> RetargetPixel:
    if kind not in KIND_VALUES:
        raise BadRequest(f"Invalid pixel kind: {kind}")
    row = RetargetPixel(
        workspace_id=workspace_id,
        kind=kind,
        pixel_id=pixel_id,
        name=name,
        is_active=is_active,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def _load(
    db: AsyncSession, *, workspace_id: UUID | None, pixel_row_id: UUID
) -> RetargetPixel:
    stmt = select(RetargetPixel).where(RetargetPixel.id == pixel_row_id)
    if workspace_id is not None:
        stmt = stmt.where(RetargetPixel.workspace_id == workspace_id)
    row = await db.scalar(stmt)
    if not row:
        raise NotFound("Pixel not found")
    return row


async def get(
    db: AsyncSession, *, workspace_id: UUID | None, pixel_row_id: UUID
) -> RetargetPixel:
    return await _load(db, workspace_id=workspace_id, pixel_row_id=pixel_row_id)


async def update(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    pixel_row_id: UUID,
    patch: dict,
) -> RetargetPixel:
    row = await _load(db, workspace_id=workspace_id, pixel_row_id=pixel_row_id)
    if "kind" in patch and patch["kind"] is not None and patch["kind"] not in KIND_VALUES:
        raise BadRequest(f"Invalid pixel kind: {patch['kind']}")
    for k, v in patch.items():
        if v is None:
            continue
        if hasattr(row, k):
            setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return row


async def delete(
    db: AsyncSession, *, workspace_id: UUID | None, pixel_row_id: UUID
) -> None:
    row = await _load(db, workspace_id=workspace_id, pixel_row_id=pixel_row_id)
    await db.delete(row)
    await db.flush()


async def list_for_workspace(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    offset: int,
    limit: int,
) -> tuple[list[RetargetPixel], int]:
    base = select(RetargetPixel)
    if workspace_id is not None:
        base = base.where(RetargetPixel.workspace_id == workspace_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(RetargetPixel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


# ---- attach / detach -------------------------------------------------

async def _assert_url(
    db: AsyncSession, *, workspace_id: UUID | None, url_id: UUID
) -> Url:
    stmt = select(Url).where(Url.id == url_id)
    if workspace_id is not None:
        stmt = stmt.where(Url.workspace_id == workspace_id)
    row = await db.scalar(stmt)
    if not row:
        raise NotFound("URL not found")
    return row


async def _assert_pixels_in_workspace(
    db: AsyncSession, *, workspace_id: UUID | None, pixel_ids: list[UUID]
) -> list[UUID]:
    if not pixel_ids:
        return []
    stmt = select(RetargetPixel.id).where(RetargetPixel.id.in_(pixel_ids))
    if workspace_id is not None:
        stmt = stmt.where(RetargetPixel.workspace_id == workspace_id)
    rows = (await db.execute(stmt)).scalars().all()
    found = set(rows)
    missing = [p for p in pixel_ids if p not in found]
    if missing:
        raise NotFound(f"Pixel(s) not found: {[str(m) for m in missing]}")
    return list(found)


async def attach(
    db: AsyncSession,
    cache_redis: Redis,
    *,
    workspace_id: UUID | None,
    url_id: UUID,
    pixel_ids: list[UUID],
) -> list[UUID]:
    await _assert_url(db, workspace_id=workspace_id, url_id=url_id)
    valid = await _assert_pixels_in_workspace(
        db, workspace_id=workspace_id, pixel_ids=pixel_ids
    )
    # Idempotent upsert — fetch current, only insert the diff.
    existing = {
        r
        for r in (
            await db.execute(
                select(link_pixels.c.pixel_id).where(link_pixels.c.url_id == url_id)
            )
        ).scalars().all()
    }
    to_add = [pid for pid in valid if pid not in existing]
    if to_add:
        await db.execute(
            link_pixels.insert(),
            [{"url_id": url_id, "pixel_id": pid} for pid in to_add],
        )
    await db.flush()
    await url_service.rewrite_pixel_cache(db, cache_redis, url_id=url_id)
    return valid


async def detach(
    db: AsyncSession,
    cache_redis: Redis,
    *,
    workspace_id: UUID | None,
    url_id: UUID,
    pixel_id: UUID,
) -> None:
    await _assert_url(db, workspace_id=workspace_id, url_id=url_id)
    await db.execute(
        link_pixels.delete().where(
            (link_pixels.c.url_id == url_id)
            & (link_pixels.c.pixel_id == pixel_id)
        )
    )
    await db.flush()
    await url_service.rewrite_pixel_cache(db, cache_redis, url_id=url_id)


async def list_for_link(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    url_id: UUID,
) -> list[RetargetPixel]:
    await _assert_url(db, workspace_id=workspace_id, url_id=url_id)
    stmt = (
        select(RetargetPixel)
        .join(link_pixels, link_pixels.c.pixel_id == RetargetPixel.id)
        .where(link_pixels.c.url_id == url_id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)
