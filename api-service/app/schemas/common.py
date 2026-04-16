"""Common response envelopes (INTEGRATION_CONTRACT section 7)."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Meta(BaseModel):
    page: int = 1
    per_page: int = 20
    total: int = 0


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    meta: Meta | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    meta: Meta


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    code: str
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorBody


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1, le=10_000)
    per_page: int = Field(default=20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


def ok(data: Any, meta: Meta | None = None) -> dict[str, Any]:
    """Build a plain-dict success envelope (for ad-hoc handlers)."""
    body: dict[str, Any] = {"success": True, "data": data}
    if meta is not None:
        body["meta"] = meta.model_dump() if isinstance(meta, Meta) else meta
    return body
