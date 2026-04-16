"""Workspace listing + active-workspace switch."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.workspace import WorkspaceOut, WorkspaceSwitchIn
from app.services import workspace_service

router = APIRouter()
# `auth_router` hosts the /auth/switch-workspace endpoint so the URL space
# groups sensibly under /api/v1/auth.
auth_router = APIRouter()
ReadScope = Security(get_current_user, scopes=["urls:read"])
WriteScope = Security(get_current_user, scopes=["urls:write"])


@router.get("/me")
async def list_mine(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, ReadScope] = ...,
):
    rows = await workspace_service.list_mine(db, user)
    return {
        "success": True,
        "data": [WorkspaceOut.model_validate(r) for r in rows],
    }


@auth_router.post("/switch-workspace")
async def switch_workspace(
    body: WorkspaceSwitchIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    access, expires_in, ws, role = await workspace_service.switch(
        db, user=user, workspace_id=body.workspace_id
    )
    return {
        "success": True,
        "data": {
            "access_token": access,
            "token_type": "bearer",
            "expires_in": expires_in,
            "workspace": WorkspaceOut.model_validate(
                {
                    "id": ws.id,
                    "name": ws.name,
                    "slug": ws.slug,
                    "plan": ws.plan,
                    "role": role,
                }
            ),
        },
    }
