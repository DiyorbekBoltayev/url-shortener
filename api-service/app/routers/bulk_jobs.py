"""Bulk jobs router — list/get + enqueue import/export/bulk-patch."""
from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import (
    get_app_redis,
    get_current_user,
    get_db,
    primary_workspace_id,
)
from app.exceptions import BadRequest
from app.models.user import User
from app.schemas.bulk_job import (
    BulkJobOut,
    BulkPatchRequest,
    ExportRequest,
)
from app.schemas.common import Meta, Pagination
from app.services import bulk_job_service

router = APIRouter()
# Mounted under /api/v1/links for the import/export/bulk-patch endpoints.
links_router = APIRouter()
WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])

# 5 MiB CSV cap — prevents accidental multi-GB uploads from hanging the
# API process while we base64-embed the blob for the worker.
_CSV_MAX_BYTES = 5 * 1024 * 1024


@router.get("")
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await bulk_job_service.list_recent(
        db, workspace_id=ws, offset=pag.offset, limit=pag.limit
    )
    return {
        "success": True,
        "data": [BulkJobOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, ReadScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await bulk_job_service.get(db, workspace_id=ws, job_id=job_id)
    return {"success": True, "data": BulkJobOut.model_validate(row)}


@links_router.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def import_links(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_app_redis),
    file: UploadFile = File(...),
    column_map: str | None = Form(default=None),
    default_tag: str | None = Form(default=None),
    default_folder_id: str | None = Form(default=None),
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    content = await file.read()
    if len(content) > _CSV_MAX_BYTES:
        raise BadRequest(
            f"CSV exceeds max size ({_CSV_MAX_BYTES} bytes)",
            code="CSV_TOO_LARGE",
        )
    col_map: dict[str, str] | None = None
    if column_map:
        try:
            parsed = json.loads(column_map)
        except Exception as exc:  # noqa: BLE001
            raise BadRequest(
                f"column_map is not valid JSON: {exc}",
                code="INVALID_COLUMN_MAP",
            ) from exc
        if not isinstance(parsed, dict):
            raise BadRequest("column_map must be a JSON object")
        col_map = {str(k): str(v) for k, v in parsed.items()}
    folder_uuid: UUID | None = None
    if default_folder_id:
        try:
            folder_uuid = UUID(default_folder_id)
        except ValueError as exc:
            raise BadRequest("default_folder_id must be a UUID") from exc
    row = await bulk_job_service.enqueue_import(
        db,
        redis,
        workspace_id=ws,
        user_id=user.id,
        csv_content=content,
        column_map=col_map,
        default_tag=default_tag,
        default_folder_id=folder_uuid,
    )
    return {"success": True, "data": BulkJobOut.model_validate(row)}


@links_router.post("/export", status_code=status.HTTP_202_ACCEPTED)
async def export_links(
    body: ExportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_app_redis),
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await bulk_job_service.enqueue_export(
        db,
        redis,
        workspace_id=ws,
        user_id=user.id,
        filter_=body.filter.model_dump(exclude_none=True),
        fmt=body.format,
    )
    return {"success": True, "data": BulkJobOut.model_validate(row)}


@links_router.post("/bulk-patch", status_code=status.HTTP_202_ACCEPTED)
async def bulk_patch(
    body: BulkPatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_app_redis),
    user: Annotated[User, WriteScope] = ...,
):
    ws = await primary_workspace_id(db, user)
    row = await bulk_job_service.enqueue_bulk_patch(
        db,
        redis,
        workspace_id=ws,
        user_id=user.id,
        url_ids=body.ids,
        patch=body.patch.model_dump(exclude_none=True),
    )
    return {"success": True, "data": BulkJobOut.model_validate(row)}
