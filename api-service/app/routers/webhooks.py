"""Webhooks router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_current_workspace, get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.common import Meta, Pagination
from app.schemas.webhook import WebhookCreate, WebhookOut, WebhookUpdate
from app.services import webhook_service

router = APIRouter()
WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    row = await webhook_service.create_webhook(
        db,
        workspace_id=workspace.id,
        url=str(body.url),
        events=body.events,
    )
    return {"success": True, "data": WebhookOut.model_validate(row)}


@router.get("")
async def list_webhooks(
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await webhook_service.list_webhooks(
        db, workspace_id=workspace.id, offset=pag.offset, limit=pag.limit
    )
    return {
        "success": True,
        "data": [WebhookOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: UUID,
    body: WebhookUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    row = await webhook_service.update_webhook(
        db,
        workspace_id=workspace.id,
        webhook_id=webhook_id,
        url=str(body.url) if body.url else None,
        events=body.events,
        is_active=body.is_active,
    )
    return {"success": True, "data": WebhookOut.model_validate(row)}


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    ok = await webhook_service.deliver_test(
        db, workspace_id=workspace.id, webhook_id=webhook_id
    )
    return {"success": True, "data": {"ok": ok}}


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    await webhook_service.delete_webhook(
        db, workspace_id=workspace.id, webhook_id=webhook_id
    )
    return None
