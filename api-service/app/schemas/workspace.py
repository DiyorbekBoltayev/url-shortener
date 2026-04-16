"""Workspace schemas."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    plan: str
    role: str | None = None


class WorkspaceSwitchIn(BaseModel):
    workspace_id: UUID
