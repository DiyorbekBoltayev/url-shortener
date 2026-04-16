"""Retarget pixels router — CRUD + attach/detach to URLs."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import (
    get_cache_redis,
    get_current_user,
    get_db,
    primary_workspace_id,
)
from app.models.user import User
from app.schemas.common import Meta, Pagination
from app.schemas.pixel import (
    PixelAttachIn,
    PixelCreate,
    PixelOut,
    PixelUpdate,
)
from app.services import pixel_service

router = APIRouter()
# `urls_router` is mounted under /api/v1/urls and exposes
# /urls/{id}/pixels endpoints colocated with the URL resource.
urls_router = APIRouter()
WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])


# ---- /api/v1/pixels CRUD ---------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_pixel(
    body: PixelCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await pixel_service.create(
        db,
        workspace_id=ws,
        kind=body.kind,
        pixel_id=body.pixel_id,
        name=body.name,
        is_active=body.is_active,
    )
    return {"success": True, "data": PixelOut.model_validate(row)}


@router.get("")
async def list_pixels(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await pixel_service.list_for_workspace(
        db, workspace_id=ws, offset=pag.offset, limit=pag.limit
    )
    return {
        "success": True,
        "data": [PixelOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }


@router.get("/{pixel_row_id}")
async def get_pixel(
    pixel_row_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await pixel_service.get(db, workspace_id=ws, pixel_row_id=pixel_row_id)
    return {"success": True, "data": PixelOut.model_validate(row)}


@router.patch("/{pixel_row_id}")
async def update_pixel(
    pixel_row_id: UUID,
    body: PixelUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await pixel_service.update(
        db,
        workspace_id=ws,
        pixel_row_id=pixel_row_id,
        patch=body.model_dump(exclude_unset=True),
    )
    return {"success": True, "data": PixelOut.model_validate(row)}


@router.delete("/{pixel_row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pixel(
    pixel_row_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    await pixel_service.delete(db, workspace_id=ws, pixel_row_id=pixel_row_id)
    return None


# ---- /api/v1/urls/{id}/pixels ----------------------------------------

@urls_router.get("/{url_id}/pixels")
async def list_link_pixels(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    rows = await pixel_service.list_for_link(db, workspace_id=ws, url_id=url_id)
    return {"success": True, "data": [PixelOut.model_validate(r) for r in rows]}


@urls_router.post("/{url_id}/pixels")
async def attach_pixels(
    url_id: UUID,
    body: PixelAttachIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    attached = await pixel_service.attach(
        db, cache, workspace_id=ws, url_id=url_id, pixel_ids=body.pixel_ids
    )
    return {"success": True, "data": {"attached": [str(p) for p in attached]}}


@urls_router.delete(
    "/{url_id}/pixels/{pixel_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def detach_pixel(
    url_id: UUID,
    pixel_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    await pixel_service.detach(
        db, cache, workspace_id=ws, url_id=url_id, pixel_id=pixel_id
    )
    return None
