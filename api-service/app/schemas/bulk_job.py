"""Bulk job schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BulkJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID | None
    user_id: UUID | None
    kind: str
    status: str
    total: int
    done: int
    failed: int
    params: dict[str, Any] | None = None
    result_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ImportRequest(BaseModel):
    """Optional JSON body accompanying the multipart CSV upload.

    ``column_map`` lets the user tell us which CSV column maps to which
    URL field (long_url is the only required target).
    """

    column_map: dict[str, str] | None = None
    default_tag: str | None = Field(default=None, max_length=64)
    default_folder_id: UUID | None = None


class ExportFilter(BaseModel):
    folder_id: UUID | None = None
    tags: list[str] | None = None
    q: str | None = Field(default=None, max_length=200)


class ExportRequest(BaseModel):
    filter: ExportFilter = Field(default_factory=ExportFilter)
    format: Literal["csv"] = "csv"


class BulkPatch(BaseModel):
    tag: str | None = Field(default=None, max_length=64)
    folder_id: UUID | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


class BulkPatchRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=1000)
    patch: BulkPatch
