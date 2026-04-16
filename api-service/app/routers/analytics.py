"""Analytics router — matches admin-panel contract (range-based + url_id-based).

Frontend uses `url_id` (UUID) to identify links; we resolve to `short_code`
before issuing ClickHouse queries. All responses follow the envelope
`{success, data}` shape.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_ch, get_current_user, get_db
from app.models.user import User
from app.services import analytics_service, url_service

router = APIRouter()

Scope = Security(get_current_user, scopes=["analytics:read"])

Range = Literal["24h", "7d", "30d", "90d"]


def _range_to_since(range_: Range) -> tuple[date, str]:
    """Return (since, granularity) for a UI range string."""
    today = date.today()
    if range_ == "24h":
        return today - timedelta(days=1), "hour"
    if range_ == "7d":
        return today - timedelta(days=7), "day"
    if range_ == "30d":
        return today - timedelta(days=30), "day"
    return today - timedelta(days=90), "day"


async def _resolve_short_code(
    db: AsyncSession, url_id: UUID, user_id: UUID
) -> str:
    row = await url_service.get_url(db, url_id=url_id, user_id=user_id)
    return row.short_code


# ---------------- Overview --------------------------------------------


@router.get("/overview")
async def overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    user: Annotated[User, Scope] = ...,
):
    """Dashboard summary for the authenticated user.

    Returns totals (all time + last 7d), top 5 links, average CTR.
    """
    all_rows, total_urls = await url_service.list_urls(
        db, user_id=user.id, workspace_id=None, offset=0, limit=10_000
    )
    active_links = sum(1 for r in all_rows if r.is_active)
    codes = [r.short_code for r in all_rows]

    total_clicks = 0
    clicks_last_7d = 0
    top_links: list[dict] = []
    top_referrers: list[dict] = []
    weekly_timeseries: list[dict] = []
    avg_ctr = 0.0
    try:
        if codes:
            (
                total_clicks,
                clicks_last_7d,
                per_code,
            ) = await analytics_service.overview(ch, short_codes=codes)
            # Build top 5 links (by clicks) with titles/long_urls from Postgres
            code_to_row = {r.short_code: r for r in all_rows}
            sorted_codes = sorted(
                per_code.items(), key=lambda kv: kv[1], reverse=True
            )[:5]
            for code, clicks in sorted_codes:
                row = code_to_row.get(code)
                if row is None:
                    continue
                top_links.append(
                    {
                        "id": str(row.id),
                        "short_code": row.short_code,
                        "long_url": row.long_url,
                        "title": row.title,
                        "clicks": int(clicks),
                    }
                )
            # avg CTR placeholder — we don't track impressions. Use ratio
            # of clicked links to total links as a weak proxy.
            clicked = sum(1 for v in per_code.values() if v > 0)
            avg_ctr = round(clicked / total_urls, 4) if total_urls else 0.0

            # Workspace-wide aggregates over last 7d — cheap because the
            # filter is already on the short_codes array the user owns.
            try:
                top_referrers = await analytics_service.top_referrers(
                    ch, short_codes=codes, limit=5
                )
            except Exception:
                top_referrers = []
            try:
                weekly_timeseries = await analytics_service.weekly_timeseries(
                    ch, short_codes=codes
                )
            except Exception:
                weekly_timeseries = []
    except Exception:
        # ClickHouse down — still return Postgres-backed fields.
        pass

    return {
        "success": True,
        "data": {
            "total_urls": total_urls,
            "total_links": total_urls,  # alias for compatibility
            "active_links": active_links,
            "total_clicks": total_clicks,
            "clicks_last_7d": clicks_last_7d,
            "clicks_this_week": clicks_last_7d,  # alias
            "top_links": top_links,
            "top_referrers": top_referrers,
            "weekly_timeseries": weekly_timeseries,
            "avg_ctr": avg_ctr,
        },
    }


# ---------------- Per-URL panels --------------------------------------


@router.get("/urls/{url_id}/timeseries")
async def timeseries(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    range: Range = Query("7d"),
    user: Annotated[User, Scope] = ...,
):
    since, granularity = _range_to_since(range)
    short_code = await _resolve_short_code(db, url_id, user.id)
    rows = await analytics_service.timeseries(
        ch,
        short_code=short_code,
        since=since,
        until=date.today(),
        bucket=granularity,
    )
    return {
        "success": True,
        "data": {
            "points": [
                {"t": r["t"], "clicks": int(r["c"])} for r in rows
            ],
            "granularity": granularity,
        },
    }


@router.get("/urls/{url_id}/geo")
async def geo(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    range: Range = Query("7d"),
    user: Annotated[User, Scope] = ...,
):
    since, _ = _range_to_since(range)
    short_code = await _resolve_short_code(db, url_id, user.id)
    rows = await analytics_service.geo(
        ch, short_code=short_code, since=since
    )
    out = []
    for r in rows:
        country_name = r.get("country") or "Unknown"
        # Use whatever code the worker persisted. Fall back to first 2
        # letters uppercased for legacy rows missing country_code.
        code = r.get("country_code")
        if not code:
            code = (
                country_name[:2].upper()
                if country_name and country_name != "Unknown"
                else "XX"
            )
        out.append(
            {
                "country_code": code,
                "country_name": country_name,
                "clicks": int(r["clicks"]),
            }
        )
    return {"success": True, "data": out}


@router.get("/urls/{url_id}/referrers")
async def referrers(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    range: Range = Query("7d"),
    user: Annotated[User, Scope] = ...,
):
    since, _ = _range_to_since(range)
    short_code = await _resolve_short_code(db, url_id, user.id)
    rows = await analytics_service.referrers(
        ch, short_code=short_code, since=since
    )
    return {
        "success": True,
        "data": [
            {
                "referer_domain": r.get("referer_domain") or r.get("referrer") or "direct",
                "clicks": int(r["clicks"]),
            }
            for r in rows
        ],
    }


@router.get("/urls/{url_id}/devices")
async def devices(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    range: Range = Query("7d"),
    user: Annotated[User, Scope] = ...,
):
    since, _ = _range_to_since(range)
    short_code = await _resolve_short_code(db, url_id, user.id)
    rows = await analytics_service.devices(
        ch, short_code=short_code, since=since
    )
    # Aggregate {device_type, os, browser} → {device_type, clicks}
    agg: dict[str, int] = {}
    for r in rows:
        key = r.get("device_type") or r.get("device") or "unknown"
        agg[key] = agg.get(key, 0) + int(r["clicks"])
    return {
        "success": True,
        "data": [
            {"device_type": d, "clicks": c}
            for d, c in sorted(agg.items(), key=lambda x: -x[1])
        ],
    }
