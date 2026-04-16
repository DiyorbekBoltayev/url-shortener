"""Workspace service — list memberships + switch active workspace."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import Forbidden, NotFound
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import jwt_service


async def list_mine(db: AsyncSession, user: User) -> list[dict]:
    """Return workspaces the user is a member of, including role + plan.

    Primary result keyed off ``workspace_members`` so we know the role.
    Workspaces owned by the user but missing a members row are appended
    with role=``owner`` (legacy rows from pre-members users).
    """
    rows = (
        await db.execute(
            select(Workspace, WorkspaceMember.role)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Workspace.id,
            )
            .where(WorkspaceMember.user_id == user.id)
        )
    ).all()
    out: list[dict] = []
    seen: set[UUID] = set()
    for ws, role in rows:
        out.append(
            {
                "id": ws.id,
                "name": ws.name,
                "slug": ws.slug,
                "plan": ws.plan,
                "role": role,
            }
        )
        seen.add(ws.id)
    owner_rows = (
        await db.execute(select(Workspace).where(Workspace.owner_id == user.id))
    ).scalars().all()
    for ws in owner_rows:
        if ws.id in seen:
            continue
        out.append(
            {
                "id": ws.id,
                "name": ws.name,
                "slug": ws.slug,
                "plan": ws.plan,
                "role": "owner",
            }
        )
    return out


async def _resolve_membership(
    db: AsyncSession, *, user: User, workspace_id: UUID
) -> tuple[Workspace, str]:
    ws = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if not ws:
        raise NotFound("Workspace not found")
    role = await db.scalar(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if role is None and ws.owner_id != user.id:
        raise Forbidden("Not a member of this workspace")
    return ws, role or "owner"


async def switch(
    db: AsyncSession, *, user: User, workspace_id: UUID
) -> tuple[str, int, Workspace, str]:
    """Mint a new access token with ``workspace_id`` claim set.

    Refresh tokens stay valid — only the access token carries workspace.
    Returns ``(access_token, expires_in, workspace, role)``.
    """
    ws, role = await _resolve_membership(
        db, user=user, workspace_id=workspace_id
    )
    scopes = ["urls:read", "urls:write", "analytics:read"]
    if user.plan == "enterprise":
        scopes.append("admin")
    access, _ = jwt_service.issue_access(
        sub=str(user.id),
        workspace_id=str(ws.id),
        plan=user.plan,
        scopes=scopes,
    )
    from app.config import settings  # local import — avoids circular init

    return access, settings.access_ttl_seconds, ws, role
