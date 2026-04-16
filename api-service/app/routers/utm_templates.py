"""UTM templates router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, primary_workspace_id
from app.models.user import User
from app.schemas.common import Meta, Pagination
from app.schemas.utm_template import (
    UTMTemplateCreate,
    UTMTemplateOut,
    UTMTemplateUpdate,
)
from app.services import utm_template_service

router = APIRouter()
WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_template(
    body: UTMTemplateCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await utm_template_service.create(
        db,
        workspace_id=ws,
        user_id=user.id,
        **body.model_dump(),
    )
    return {"success": True, "data": UTMTemplateOut.model_validate(row)}


@router.get("")
async def list_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await utm_template_service.list_for_workspace(
        db, workspace_id=ws, offset=pag.offset, limit=pag.limit
    )
    return {
        "success": True,
        "data": [UTMTemplateOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }


@router.get("/{template_id}")
async def get_template(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await utm_template_service.get(
        db, workspace_id=ws, template_id=template_id
    )
    return {"success": True, "data": UTMTemplateOut.model_validate(row)}


@router.patch("/{template_id}")
async def update_template(
    template_id: UUID,
    body: UTMTemplateUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await utm_template_service.update(
        db,
        workspace_id=ws,
        template_id=template_id,
        patch=body.model_dump(exclude_unset=True),
    )
    return {"success": True, "data": UTMTemplateOut.model_validate(row)}


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    await utm_template_service.delete(
        db, workspace_id=ws, template_id=template_id
    )
    return None
