"""Domains router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_current_workspace, get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.common import Meta, Pagination
from app.schemas.domain import DomainCreate, DomainOut
from app.services import domain_service

router = APIRouter()
WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_domain(
    body: DomainCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    row = await domain_service.create_domain(
        db, workspace_id=workspace.id, domain=body.domain
    )
    return {"success": True, "data": DomainOut.model_validate(row)}


@router.get("")
async def list_domains(
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await domain_service.list_domains(
        db, workspace_id=workspace.id, offset=pag.offset, limit=pag.limit
    )
    return {
        "success": True,
        "data": [DomainOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(
    domain_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    await domain_service.delete_domain(db, workspace_id=workspace.id, domain_id=domain_id)
    return None


@router.post("/{domain_id}/verify")
async def verify(
    domain_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    row = await domain_service.verify_domain(
        db, workspace_id=workspace.id, domain_id=domain_id
    )
    return {"success": True, "data": DomainOut.model_validate(row)}
