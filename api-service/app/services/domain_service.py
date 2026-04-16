"""Domain service — add, list, verify, delete."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import Conflict, NotFound
from app.models.domain import Domain


def _gen_dns_token() -> str:
    """Token the user must set as TXT `_shortener-verify.{domain}`."""
    return "verify-" + secrets.token_urlsafe(24)


async def create_domain(
    db: AsyncSession, *, workspace_id: UUID, domain: str
) -> Domain:
    row = Domain(
        workspace_id=workspace_id,
        domain=domain.lower(),
        dns_token=_gen_dns_token(),
    )
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise Conflict("Domain already exists") from exc
    await db.refresh(row)
    return row


async def list_domains(
    db: AsyncSession, *, workspace_id: UUID, offset: int, limit: int
) -> tuple[list[Domain], int]:
    base = select(Domain).where(Domain.workspace_id == workspace_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(base.order_by(Domain.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)


async def delete_domain(db: AsyncSession, *, workspace_id: UUID, domain_id: UUID) -> None:
    row = await db.scalar(
        select(Domain).where(Domain.id == domain_id, Domain.workspace_id == workspace_id)
    )
    if not row:
        raise NotFound("Domain not found")
    await db.delete(row)
    await db.flush()


async def verify_domain(db: AsyncSession, *, workspace_id: UUID, domain_id: UUID) -> Domain:
    """Mark a domain verified (stub — real implementation performs DNS TXT lookup)."""
    row = await db.scalar(
        select(Domain).where(Domain.id == domain_id, Domain.workspace_id == workspace_id)
    )
    if not row:
        raise NotFound("Domain not found")
    row.is_verified = True
    row.verified_at = datetime.now(timezone.utc)
    row.ssl_status = "active"
    await db.flush()
    await db.refresh(row)
    return row
