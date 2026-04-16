"""Webhook schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(min_length=1, max_length=20)
    workspace_id: UUID | None = None


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    url: str
    events: list[str]
    is_active: bool
    last_triggered: datetime | None
    failure_count: int
    created_at: datetime
