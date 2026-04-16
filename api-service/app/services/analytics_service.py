"""Analytics — ClickHouse read queries.

All queries use parameterised placeholders (``{name:Type}``) — never f-strings
or string interpolation. Arrays are passed via ``Array(String)`` parameters.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from clickhouse_connect.driver.asyncclient import AsyncClient


async def _rows(ch: AsyncClient, sql: str, **params: Any) -> list[tuple]:
    result = await ch.query(sql, parameters=params)
    return list(result.result_rows)


async def summary(ch: AsyncClient, *, short_code: str, since: date) -> dict[str, Any]:
    rows = await _rows(
        ch,
        """
        SELECT count() AS clicks,
               uniq(ip_hash) AS uniques,
               countIf(is_bot) AS bot_clicks,
               uniqIf(ip_hash, not is_bot) AS real_uniques
          FROM clicks
         WHERE short_code = {sc:String}
           AND clicked_at >= {since:Date}
        """,
        sc=short_code,
        since=since,
    )
    c, u, b, ru = rows[0] if rows else (0, 0, 0, 0)
    return {
        "short_code": short_code,
        "clicks": int(c),
        "uniques": int(u),
        "bot_clicks": int(b),
        "real_uniques": int(ru),
    }


async def timeseries(
    ch: AsyncClient,
    *,
    short_code: str,
    since: date,
    until: date,
    bucket: str = "day",
) -> list[dict[str, Any]]:
    step = "toStartOfHour(clicked_at)" if bucket == "hour" else "toDate(clicked_at)"
    # Use half-open range with b+1 so today's clicks (with time-of-day > 00:00)
    # are included. A plain BETWEEN against Date casts the end to midnight and
    # drops same-day data.
    rows = await _rows(
        ch,
        f"""
        SELECT {step} AS t, count() AS c
          FROM clicks
         WHERE short_code = {{sc:String}}
           AND clicked_at >= {{a:Date}}
           AND clicked_at < addDays({{b:Date}}, 1)
         GROUP BY t
         ORDER BY t
        """,
        sc=short_code,
        a=since,
        b=until,
    )
    return [{"t": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]),
             "c": int(r[1])} for r in rows]


async def geo(
    ch: AsyncClient,
    *,
    short_code: str,
    since: date | None = None,
) -> list[dict[str, Any]]:
    since = since or (date.today() - timedelta(days=7))
    rows = await _rows(
        ch,
        """
        SELECT country_code, any(country_name), count() AS c
          FROM clicks
         WHERE short_code = {sc:String}
           AND clicked_at >= {since:Date}
         GROUP BY country_code
         ORDER BY c DESC
         LIMIT 50
        """,
        sc=short_code,
        since=since,
    )
    return [
        {"country_code": r[0] or "XX", "country_name": r[1] or "Unknown", "clicks": int(r[2])}
        for r in rows
    ]


async def devices(
    ch: AsyncClient,
    *,
    short_code: str,
    since: date | None = None,
) -> list[dict[str, Any]]:
    since = since or (date.today() - timedelta(days=7))
    rows = await _rows(
        ch,
        """
        SELECT device_type, os, browser, count() AS c
          FROM clicks
         WHERE short_code = {sc:String}
           AND clicked_at >= {since:Date}
         GROUP BY device_type, os, browser
         ORDER BY c DESC
         LIMIT 100
        """,
        sc=short_code,
        since=since,
    )
    return [
        {"device_type": r[0] or "unknown", "os": r[1] or "unknown",
         "browser": r[2] or "unknown", "clicks": int(r[3])}
        for r in rows
    ]


async def referrers(
    ch: AsyncClient,
    *,
    short_code: str,
    since: date | None = None,
) -> list[dict[str, Any]]:
    since = since or (date.today() - timedelta(days=7))
    rows = await _rows(
        ch,
        """
        SELECT referer_domain, count() AS c
          FROM clicks
         WHERE short_code = {sc:String}
           AND clicked_at >= {since:Date}
         GROUP BY referer_domain
         ORDER BY c DESC
         LIMIT 50
        """,
        sc=short_code,
        since=since,
    )
    return [{"referer_domain": r[0] or "direct", "clicks": int(r[1])} for r in rows]


async def dashboard(ch: AsyncClient, *, workspace_id: str) -> dict[str, Any]:
    """Aggregate dashboard summary across a workspace (best-effort)."""
    rows = await _rows(
        ch,
        """
        SELECT count() AS clicks,
               uniq(short_code) AS links,
               uniq(ip_hash) AS uniques
          FROM clicks
         WHERE workspace_id = {ws:String}
           AND clicked_at >= today() - 30
        """,
        ws=workspace_id,
    )
    c, l, u = rows[0] if rows else (0, 0, 0)
    return {"clicks_30d": int(c), "active_links_30d": int(l), "uniques_30d": int(u)}


async def overview(
    ch: AsyncClient, *, short_codes: list[str]
) -> tuple[int, int, dict[str, int]]:
    """Aggregate overview across the caller's short codes.

    Returns ``(total_clicks_all_time, total_clicks_last_7d, per_code)``.
    ``per_code`` is a ``{short_code: clicks_all_time}`` map used to build
    the top-links list. Uses a parameterised ``Array(String)`` to avoid
    any SQL injection risk.
    """
    if not short_codes:
        return 0, 0, {}

    # Totals (all time)
    total_rows = await _rows(
        ch,
        """
        SELECT count()
          FROM clicks
         WHERE short_code IN {codes:Array(String)}
        """,
        codes=short_codes,
    )
    total_clicks = int(total_rows[0][0]) if total_rows else 0

    # Last 7 days
    week_rows = await _rows(
        ch,
        """
        SELECT count()
          FROM clicks
         WHERE short_code IN {codes:Array(String)}
           AND clicked_at >= today() - 7
        """,
        codes=short_codes,
    )
    clicks_last_7d = int(week_rows[0][0]) if week_rows else 0

    # Per-code counts to build the top-links list
    per_rows = await _rows(
        ch,
        """
        SELECT short_code, count() AS c
          FROM clicks
         WHERE short_code IN {codes:Array(String)}
         GROUP BY short_code
        """,
        codes=short_codes,
    )
    per_code = {r[0]: int(r[1]) for r in per_rows}

    return total_clicks, clicks_last_7d, per_code


async def top_referrers(
    ch: AsyncClient, *, short_codes: list[str], limit: int = 5
) -> list[dict[str, Any]]:
    """Top referrers across a set of short_codes (last 7d)."""
    if not short_codes:
        return []
    rows = await _rows(
        ch,
        """
        SELECT referer_domain, count() AS c
          FROM clicks
         WHERE short_code IN {codes:Array(String)}
           AND clicked_at >= today() - 7
         GROUP BY referer_domain
         ORDER BY c DESC
         LIMIT {limit:UInt32}
        """,
        codes=short_codes,
        limit=limit,
    )
    return [
        {"referer": r[0] or "direct", "clicks": int(r[1])}
        for r in rows
    ]


async def weekly_timeseries(
    ch: AsyncClient, *, short_codes: list[str]
) -> list[dict[str, Any]]:
    """Workspace-wide daily click counts for the last 7 days."""
    if not short_codes:
        return []
    rows = await _rows(
        ch,
        """
        SELECT toDate(clicked_at) AS t, count() AS c
          FROM clicks
         WHERE short_code IN {codes:Array(String)}
           AND clicked_at >= today() - 7
           AND clicked_at < addDays(today(), 1)
         GROUP BY t
         ORDER BY t
        """,
        codes=short_codes,
    )
    return [
        {"t": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]),
         "clicks": int(r[1])}
        for r in rows
    ]


async def click_totals(
    ch: AsyncClient, *, short_codes: list[str]
) -> dict[str, int]:
    """Click totals per short_code (all-time). Source of truth is ClickHouse."""
    if not short_codes:
        return {}
    rows = await _rows(
        ch,
        """
        SELECT short_code, count()
          FROM clicks
         WHERE short_code IN {codes:Array(String)}
         GROUP BY short_code
        """,
        codes=short_codes,
    )
    return {r[0]: int(r[1]) for r in rows}
