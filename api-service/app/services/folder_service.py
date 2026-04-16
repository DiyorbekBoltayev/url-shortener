"""Folder service — tree CRUD + link moves."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequest, Conflict, NotFound
from app.models.folder import Folder
from app.models.url import Url


async def _assert_parent(
    db: AsyncSession, *, workspace_id: UUID | None, parent_id: UUID | None
) -> None:
    """Ensure ``parent_id`` belongs to the same workspace."""
    if parent_id is None:
        return
    row = await db.scalar(select(Folder).where(Folder.id == parent_id))
    if row is None:
        raise NotFound("Parent folder not found")
    if row.workspace_id != workspace_id:
        raise BadRequest("Parent folder belongs to a different workspace")


async def _assert_no_cycle(
    db: AsyncSession, *, folder_id: UUID, new_parent_id: UUID | None
) -> None:
    """Walk ancestors of ``new_parent_id``; refuse if we meet ``folder_id``."""
    if new_parent_id is None:
        return
    if new_parent_id == folder_id:
        raise BadRequest("A folder cannot be its own parent")
    seen: set[UUID] = {folder_id}
    cursor: UUID | None = new_parent_id
    for _ in range(128):  # hard depth guard
        if cursor is None:
            return
        if cursor in seen:
            raise BadRequest("Move would create a folder cycle")
        seen.add(cursor)
        cursor = await db.scalar(
            select(Folder.parent_id).where(Folder.id == cursor)
        )
    raise BadRequest("Folder tree too deep")


async def create_folder(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    user_id: UUID | None,
    name: str,
    parent_id: UUID | None,
    color: str | None,
) -> Folder:
    await _assert_parent(db, workspace_id=workspace_id, parent_id=parent_id)
    row = Folder(
        workspace_id=workspace_id,
        parent_id=parent_id,
        name=name,
        color=color,
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def update_folder(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    folder_id: UUID,
    name: str | None = None,
    parent_id: UUID | None = None,
    color: str | None = None,
    set_parent: bool = False,
) -> Folder:
    row = await _load(db, workspace_id=workspace_id, folder_id=folder_id)
    if name is not None:
        row.name = name
    if color is not None:
        row.color = color
    if set_parent:
        await _assert_parent(db, workspace_id=workspace_id, parent_id=parent_id)
        await _assert_no_cycle(
            db, folder_id=folder_id, new_parent_id=parent_id
        )
        row.parent_id = parent_id
    await db.flush()
    await db.refresh(row)
    return row


async def _load(
    db: AsyncSession, *, workspace_id: UUID | None, folder_id: UUID
) -> Folder:
    stmt = select(Folder).where(Folder.id == folder_id)
    if workspace_id is not None:
        stmt = stmt.where(Folder.workspace_id == workspace_id)
    row = await db.scalar(stmt)
    if not row:
        raise NotFound("Folder not found")
    return row


async def delete_folder(
    db: AsyncSession, *, workspace_id: UUID | None, folder_id: UUID
) -> None:
    """Delete a folder; Postgres ``ON DELETE CASCADE`` wipes children rows
    and sets ``urls.folder_id`` to NULL via the FK's ``SET NULL`` rule."""
    row = await _load(db, workspace_id=workspace_id, folder_id=folder_id)
    await db.delete(row)
    await db.flush()


async def list_folders(
    db: AsyncSession, *, workspace_id: UUID | None
) -> list[dict]:
    """Return a flat list of folders annotated with ``children_count`` and
    ``links_count`` so the frontend can render a tree without N+1."""
    stmt = select(Folder)
    if workspace_id is not None:
        stmt = stmt.where(Folder.workspace_id == workspace_id)
    stmt = stmt.order_by(Folder.created_at.asc())
    rows = (await db.execute(stmt)).scalars().all()
    ids = [r.id for r in rows]
    if not ids:
        return []

    # Children counts — aggregate by parent_id.
    children_counts: dict[UUID, int] = {}
    c_rows = (
        await db.execute(
            select(Folder.parent_id, func.count(Folder.id))
            .where(Folder.parent_id.in_(ids))
            .group_by(Folder.parent_id)
        )
    ).all()
    for pid, cnt in c_rows:
        children_counts[pid] = int(cnt)

    # Link counts — aggregate by folder_id.
    link_counts: dict[UUID, int] = {}
    l_rows = (
        await db.execute(
            select(Url.folder_id, func.count(Url.id))
            .where(Url.folder_id.in_(ids))
            .group_by(Url.folder_id)
        )
    ).all()
    for fid, cnt in l_rows:
        link_counts[fid] = int(cnt)

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "workspace_id": r.workspace_id,
                "parent_id": r.parent_id,
                "name": r.name,
                "color": r.color,
                "created_by": r.created_by,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "children_count": children_counts.get(r.id, 0),
                "links_count": link_counts.get(r.id, 0),
            }
        )
    return out


async def get_folder(
    db: AsyncSession, *, workspace_id: UUID | None, folder_id: UUID
) -> Folder:
    return await _load(db, workspace_id=workspace_id, folder_id=folder_id)


async def list_links_in_folder(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    folder_id: UUID,
    offset: int,
    limit: int,
) -> tuple[list[Url], int]:
    await _load(db, workspace_id=workspace_id, folder_id=folder_id)
    base = select(Url).where(Url.folder_id == folder_id)
    if workspace_id is not None:
        base = base.where(Url.workspace_id == workspace_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(Url.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


async def move_link(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    url_id: UUID,
    folder_id: UUID | None,
) -> Url:
    if folder_id is not None:
        await _load(db, workspace_id=workspace_id, folder_id=folder_id)
    stmt = select(Url).where(Url.id == url_id)
    if workspace_id is not None:
        stmt = stmt.where(Url.workspace_id == workspace_id)
    url = await db.scalar(stmt)
    if url is None:
        raise NotFound("URL not found")
    url.folder_id = folder_id
    await db.flush()
    return url


async def move_links_bulk(
    db: AsyncSession,
    *,
    workspace_id: UUID | None,
    folder_id: UUID | None,
    url_ids: list[UUID],
) -> int:
    if not url_ids:
        return 0
    if folder_id is not None:
        await _load(db, workspace_id=workspace_id, folder_id=folder_id)
    stmt = update(Url).where(Url.id.in_(url_ids)).values(folder_id=folder_id)
    if workspace_id is not None:
        stmt = stmt.where(Url.workspace_id == workspace_id)
    result = await db.execute(stmt)
    await db.flush()
    return int(result.rowcount or 0)
