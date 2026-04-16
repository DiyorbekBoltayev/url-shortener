"""API-key schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    workspace_id: UUID | None = None
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    """Same as ``ApiKeyOut`` but with the one-time plaintext ``key``."""
    key: str
