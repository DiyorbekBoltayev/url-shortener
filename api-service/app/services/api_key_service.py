"""API-key service — create, list, revoke."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound
from app.models.api_key import ApiKey
from app.utils.hashing import generate_api_key, hash_key


async def create_api_key(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID | None,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
) -> tuple[ApiKey, str]:
    raw, digest, prefix = generate_api_key()
    row = ApiKey(
        user_id=user_id,
        workspace_id=workspace_id,
        name=name,
        key_hash=digest,
        key_prefix=prefix,
        scopes=list(scopes),
        expires_at=expires_at,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row, raw


async def list_api_keys(
    db: AsyncSession, *, user_id: UUID, offset: int, limit: int
) -> tuple[list[ApiKey], int]:
    base = select(ApiKey).where(ApiKey.user_id == user_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(base.order_by(ApiKey.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)


async def revoke_api_key(
    db: AsyncSession, redis: Redis, *, user_id: UUID, api_key_id: UUID
) -> None:
    row = await db.scalar(
        select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.user_id == user_id)
    )
    if not row:
        raise NotFound("API key not found")
    digest = row.key_hash
    await db.delete(row)
    await db.flush()
    # Evict cache entry so redirect-service / deps don't accept a stale key.
    try:
        await redis.delete(f"apikey:{digest}")
    except Exception:
        pass


async def touch_last_used(db: AsyncSession, *, raw_key: str) -> ApiKey | None:
    """Helper used by the API-key dependency to validate + bump last_used."""
    digest = hash_key(raw_key)
    row = await db.scalar(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.is_active.is_(True))
    )
    if row is None:
        return None
    row.last_used_at = func.now()
    await db.flush()
    return row
