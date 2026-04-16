"""Url — the primary resource."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.retarget_pixel import RetargetPixel, link_pixels


class Url(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "urls"

    short_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    long_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    domain_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("domains.id", ondelete="SET NULL"),
        nullable=True,
    )
    folder_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}", default=list, nullable=False
    )
    utm_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)

    click_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    last_clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ---- P0 features --------------------------------------------------
    routing_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    qr_style: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    preview_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    og_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    og_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    og_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    og_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    safety_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="unchecked",
        server_default="unchecked",
    )
    safety_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pixels: Mapped[list[RetargetPixel]] = relationship(
        RetargetPixel,
        secondary=link_pixels,
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_urls_user_id", "user_id"),
        Index("idx_urls_workspace_id", "workspace_id"),
        Index("idx_urls_domain_id", "domain_id"),
        Index("idx_urls_created_at", "created_at"),
        Index("idx_urls_folder", "workspace_id", "folder_id"),
    )
