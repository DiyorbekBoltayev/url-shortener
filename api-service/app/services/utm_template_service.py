"""UTM template CRUD service."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound
from app.models.utm_template import UTMTemplate


async def create(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    user_id: UUID | None,
    name: str,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    utm_term: str | None = None,
    utm_content: str | None = None,
) -> UTMTemplate:
    row = UTMTemplate(
        workspace_id=workspace_id,
        created_by=user_id,
        name=name,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        utm_term=utm_term,
        utm_content=utm_content,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def _load(
    db: AsyncSession, *, workspace_id: UUID | None, template_id: UUID
) -> UTMTemplate:
    stmt = select(UTMTemplate).where(UTMTemplate.id == template_id)
    if workspace_id is not None:
        stmt = stmt.where(UTMTemplate.workspace_id == workspace_id)
    row = await db.scalar(stmt)
    if not row:
        raise NotFound("UTM template not found")
    return row


async def get(
    db: AsyncSession, *, workspace_id: UUID | None, template_id: UUID
) -> UTMTemplate:
    return await _load(db, workspace_id=workspace_id, template_id=template_id)


async def update(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    template_id: UUID,
    patch: dict,
) -> UTMTemplate:
    row = await _load(db, workspace_id=workspace_id, template_id=template_id)
    for k, v in patch.items():
        if hasattr(row, k):
            setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return row


async def delete(
    db: AsyncSession, *, workspace_id: UUID | None, template_id: UUID
) -> None:
    row = await _load(db, workspace_id=workspace_id, template_id=template_id)
    await db.delete(row)
    await db.flush()


async def list_for_workspace(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    offset: int,
    limit: int,
) -> tuple[list[UTMTemplate], int]:
    base = select(UTMTemplate)
    if workspace_id is not None:
        base = base.where(UTMTemplate.workspace_id == workspace_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(UTMTemplate.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)
