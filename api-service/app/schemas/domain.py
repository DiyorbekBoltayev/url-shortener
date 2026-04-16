"""Domain schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DomainCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=255)


class DomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    domain: str
    is_verified: bool
    verified_at: datetime | None
    ssl_status: str
    dns_token: str | None = None
    created_at: datetime
