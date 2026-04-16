"""RetargetPixel + link_pixels association."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Table, Column, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


# Association table for urls <-> retarget_pixels (many-to-many).
link_pixels = Table(
    "link_pixels",
    Base.metadata,
    Column(
        "url_id",
        PG_UUID(as_uuid=True),
        ForeignKey("urls.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "pixel_id",
        PG_UUID(as_uuid=True),
        ForeignKey("retarget_pixels.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class RetargetPixel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "retarget_pixels"

    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    pixel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_retarget_pixels_workspace", "workspace_id"),
    )
