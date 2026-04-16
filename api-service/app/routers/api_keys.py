"""API-keys router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_app_redis, get_current_user, get_db
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.schemas.common import Meta, Pagination
from app.services import api_key_service

router = APIRouter()
WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    row, raw = await api_key_service.create_api_key(
        db,
        user_id=user.id,
        workspace_id=body.workspace_id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    return {
        "success": True,
        "data": ApiKeyCreated(
            id=row.id,
            name=row.name,
            key_prefix=row.key_prefix,
            scopes=list(row.scopes or []),
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            is_active=row.is_active,
            created_at=row.created_at,
            key=raw,
        ),
    }


@router.get("")
async def list_api_keys(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await api_key_service.list_api_keys(
        db, user_id=user.id, offset=pag.offset, limit=pag.limit
    )
    return {
        "success": True,
        "data": [ApiKeyOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_app_redis),
    user: Annotated[User, WriteScope] = ...,
):
    await api_key_service.revoke_api_key(
        db, redis, user_id=user.id, api_key_id=api_key_id
    )
    return None
