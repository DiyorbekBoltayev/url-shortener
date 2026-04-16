"""Folder schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None
    color: str | None = Field(default=None, max_length=16)


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: UUID | None = None
    color: str | None = Field(default=None, max_length=16)


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID | None
    parent_id: UUID | None
    name: str
    color: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    children_count: int = 0
    links_count: int = 0


class MoveLinksIn(BaseModel):
    """Payload for bulk-moving links into a folder."""

    ids: list[UUID] = Field(min_length=1, max_length=500)
