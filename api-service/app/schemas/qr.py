"""Branded QR-style schema (P0-2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

HEX_RE = r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"
Dots = Literal["square", "rounded", "extra-rounded"]
Corners = Literal["square", "rounded", "extra-rounded"]
Frame = Literal["none", "rounded", "square"]


class QRStyle(BaseModel):
    """User-configurable branded-QR options, persisted as ``urls.qr_style``.

    All fields are optional — missing fields fall back to sensible defaults
    (black/white, square dots, no frame, no logo) in :mod:`qr_service`.
    """

    model_config = ConfigDict(extra="forbid")

    fg: str | None = Field(default=None, max_length=7, pattern=HEX_RE)
    bg: str | None = Field(default=None, max_length=7, pattern=HEX_RE)
    logo_url: str | None = Field(default=None, max_length=500)
    frame: Frame | None = None
    dots: Dots | None = None
    corners: Corners | None = None
    eye_color: str | None = Field(default=None, max_length=7, pattern=HEX_RE)

    @field_validator("logo_url")
    @classmethod
    def _require_http(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        lower = v.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("logo_url must be http:// or https://")
        return v
