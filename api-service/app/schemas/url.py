"""URL CRUD schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.qr import QRStyle


# ---- routing_rules sub-schemas ---------------------------------------

class ABRule(BaseModel):
    url: str = Field(min_length=1, max_length=10_000)
    weight: int = Field(ge=1, le=100)


class DeviceRules(BaseModel):
    """Device-aware destinations. All fields optional; missing means fall through."""

    ios: str | None = Field(default=None, max_length=10_000)
    android: str | None = Field(default=None, max_length=10_000)
    desktop: str | None = Field(default=None, max_length=10_000)


class RoutingRules(BaseModel):
    """Full routing rules JSON — optional ab / device / geo.

    ``geo`` is a free-form dict because redirect-service is the source of
    truth on country-code matching (ISO-3166-1 alpha-2 by convention,
    plus a ``default`` fallback key).
    """

    ab: list[ABRule] | None = None
    device: DeviceRules | None = None
    geo: dict[str, str] | None = None

    @field_validator("ab")
    @classmethod
    def _weights_sum_to_100(cls, v: list[ABRule] | None) -> list[ABRule] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("ab list cannot be empty")
        total = sum(item.weight for item in v)
        if total != 100:
            raise ValueError("ab weights must sum to exactly 100")
        return v

    @model_validator(mode="after")
    def _at_least_one(self) -> "RoutingRules":
        if not any((self.ab, self.device, self.geo)):
            raise ValueError(
                "routing_rules must specify at least one of ab/device/geo"
            )
        return self


# ---- URL CRUD --------------------------------------------------------

class URLCreate(BaseModel):
    long_url: str = Field(min_length=1, max_length=10_000)
    custom_slug: str | None = Field(
        default=None, min_length=3, max_length=10, pattern=r"^[A-Za-z0-9_-]+$"
    )
    title: str | None = Field(default=None, max_length=500)
    domain_id: UUID | None = None
    folder_id: UUID | None = None
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=1, max_length=200)
    max_clicks: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list, max_length=20)
    utm_source: str | None = Field(default=None, max_length=255)
    utm_medium: str | None = Field(default=None, max_length=255)
    utm_campaign: str | None = Field(default=None, max_length=255)
    routing_rules: RoutingRules | None = None
    qr_style: QRStyle | None = None
    preview_enabled: bool | None = None


class URLUpdate(BaseModel):
    long_url: str | None = Field(default=None, min_length=1, max_length=10_000)
    title: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    folder_id: UUID | None = None
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=1, max_length=200)
    max_clicks: int | None = Field(default=None, ge=1)
    tags: list[str] | None = Field(default=None, max_length=20)
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    routing_rules: RoutingRules | None = None
    qr_style: QRStyle | None = None
    preview_enabled: bool | None = None


class URLOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    short_code: str
    long_url: str
    title: str | None
    workspace_id: UUID | None
    user_id: UUID | None
    domain_id: UUID | None
    folder_id: UUID | None = None
    is_active: bool
    expires_at: datetime | None
    max_clicks: int | None
    tags: list[str]
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    click_count: int
    last_clicked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # ---- P0 features ------------------------------------------------
    routing_rules: dict[str, Any] | None = None
    qr_style: dict[str, Any] | None = None
    preview_enabled: bool = False
    og_title: str | None = None
    og_description: str | None = None
    og_image_url: str | None = None
    favicon_url: str | None = None
    og_fetched_at: datetime | None = None
    safety_status: str = "unchecked"
    safety_reason: str | None = None
    safety_checked_at: datetime | None = None


class BulkURLCreate(BaseModel):
    urls: list[URLCreate] = Field(min_length=1, max_length=1000)


class BulkURLResult(BaseModel):
    created: list[URLOut]
    errors: list[dict]
