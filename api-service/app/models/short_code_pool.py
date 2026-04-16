"""KGS — pre-generated short-code pool."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShortCodePool(Base):
    __tablename__ = "short_code_pool"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    claimed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_pool_available", "is_used"),
    )
