"""Retarget pixel schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

KIND_VALUES = ("fb", "ga4", "gtm", "linkedin", "tiktok", "pinterest", "twitter")
PixelKind = Literal["fb", "ga4", "gtm", "linkedin", "tiktok", "pinterest", "twitter"]


class PixelCreate(BaseModel):
    kind: PixelKind
    pixel_id: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class PixelUpdate(BaseModel):
    kind: PixelKind | None = None
    pixel_id: str | None = Field(default=None, min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class PixelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID | None
    kind: str
    pixel_id: str
    name: str | None
    is_active: bool
    created_at: datetime


class PixelAttachIn(BaseModel):
    pixel_ids: list[UUID] = Field(min_length=1, max_length=20)
