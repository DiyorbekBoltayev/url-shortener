"""Folders router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, primary_workspace_id
from app.models.user import User
from app.schemas.common import Meta, Pagination
from app.schemas.folder import FolderCreate, FolderOut, FolderUpdate, MoveLinksIn
from app.schemas.url import URLOut
from app.services import folder_service

router = APIRouter()
WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])


def _folder_row_to_out(row, children: int, links: int) -> dict:
    """Build a FolderOut-compatible dict from a SQLAlchemy Folder row.

    Pydantic's ``from_attributes=True`` doesn't see ``children_count`` /
    ``links_count`` because those are not ORM columns; we stuff them in
    explicitly.
    """
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "parent_id": row.parent_id,
        "name": row.name,
        "color": row.color,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "children_count": children,
        "links_count": links,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await folder_service.create_folder(
        db,
        workspace_id=ws,
        user_id=user.id,
        name=body.name,
        parent_id=body.parent_id,
        color=body.color,
    )
    return {
        "success": True,
        "data": FolderOut.model_validate(_folder_row_to_out(row, 0, 0)),
    }


@router.get("")
async def list_folders(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    rows = await folder_service.list_folders(db, workspace_id=ws)
    return {
        "success": True,
        "data": [FolderOut.model_validate(r) for r in rows],
    }


@router.patch("/{folder_id}")
async def update_folder(
    folder_id: UUID,
    body: FolderUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    data = body.model_dump(exclude_unset=True)
    row = await folder_service.update_folder(
        db,
        workspace_id=ws,
        folder_id=folder_id,
        name=data.get("name"),
        parent_id=data.get("parent_id"),
        color=data.get("color"),
        set_parent="parent_id" in data,
    )
    return {
        "success": True,
        "data": FolderOut.model_validate(_folder_row_to_out(row, 0, 0)),
    }


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    await folder_service.delete_folder(db, workspace_id=ws, folder_id=folder_id)
    return None


@router.get("/{folder_id}/links")
async def list_folder_links(
    folder_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await folder_service.list_links_in_folder(
        db,
        workspace_id=ws,
        folder_id=folder_id,
        offset=pag.offset,
        limit=pag.limit,
    )
    return {
        "success": True,
        "data": [URLOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }


@router.post("/{folder_id}/move-links")
async def move_links(
    folder_id: UUID,
    body: MoveLinksIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    moved = await folder_service.move_links_bulk(
        db,
        workspace_id=ws,
        folder_id=folder_id,
        url_ids=body.ids,
    )
    return {"success": True, "data": {"moved": moved}}
