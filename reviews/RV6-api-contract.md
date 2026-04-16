# RV6 — API Contract Conformance Review

**Scope:** frontend API client (`admin-panel/src/app/core/api/*`, `core/auth/auth.service.ts`, `features/**`) vs backend (`api-service/app/routers/*`, `main.py`).

**Base URLs**

- Frontend: `environment.apiBaseUrl = '/api'` (`admin-panel/src/environments/environment.ts:3`) + path like `/v1/analytics/overview` → `GET /api/v1/analytics/overview`.
- Backend: routers mounted under `/api/v1/{domain}` in `api-service/app/main.py:86-93`.

So the `/api/v1` prefix assumption is consistent; every mismatch below is about path shape, method, or payload, not about the base prefix.

---

## 1. Endpoint matrix

Legend:

- **OK** — path, method, and payload contract match.
- **MISMATCH** — backend exists but route/shape differs.
- **MISSING** — backend has no corresponding endpoint at all.

| # | Frontend call (file:line) | Method | Frontend path (after `/api`) | Backend route | Status |
|---|---|---|---|---|---|
| 1 | `auth.api.ts:17` | POST | `/v1/auth/login` | `POST /api/v1/auth/login` (`routers/auth.py:64`) | **OK** |
| 2 | `auth.api.ts:21` | POST | `/v1/auth/register` | `POST /api/v1/auth/register` (`auth.py:41`) | **OK** |
| 3 | `auth.api.ts:25` / `auth.service.ts:142` | POST | `/v1/auth/refresh` | `POST /api/v1/auth/refresh` (`auth.py:85`) | **OK** |
| 4 | `auth.api.ts:29` / `auth.service.ts:167` | POST | `/v1/auth/logout` | `POST /api/v1/auth/logout` (`auth.py:102`) | **MISMATCH** — backend `LogoutIn` is *required* body (`schemas/auth.py:22`); frontend sends `{}` (no `refresh_token`). Pydantic will 422. |
| 5 | `auth.api.ts:33` / `auth.service.ts:67` / `settings.component.ts:100` | GET / PATCH | `/v1/users/me` | `GET /api/v1/users/me` (`users.py:21`), `PATCH /api/v1/users/me` (`users.py:26`) | **MISMATCH** — PATCH body: frontend sends `{full_name, email}` (`settings.component.ts:101`); backend `UserUpdate` only accepts `full_name` (`schemas/user.py:23`). Email silently dropped. |
| 6 | `settings.component.ts:117` | POST | `/auth/password` **(not `/v1/…`!)** → `/api/auth/password` | none | **MISSING** + **wrong prefix** — backend has no password-change route; path is also missing `/v1`. |
| 7 | `urls.api.ts:12` | GET | `/v1/urls` | `GET /api/v1/urls` (`urls.py:87`) | **OK** |
| 8 | `urls.api.ts:16` | GET | `/v1/urls/{id}` | `GET /api/v1/urls/{url_id}` (`urls.py:112`) | **OK** |
| 9 | `urls.api.ts:20` | POST | `/v1/urls` | `POST /api/v1/urls` (`urls.py:64`) | **MISMATCH** — frontend `CreateUrlRequest` has `password` (OK) but no `utm_*`; body also contains `tags` which backend accepts. Works, but the `UrlDto` expects `domain_id`, `click_count`, `last_clicked_at`, `is_active`, `expires_at`, `max_clicks`, `tags`, **no `workspace_id`/`user_id`/`utm_*`**, while backend `URLOut` returns `workspace_id`, `user_id`, `utm_source/medium/campaign` (extras are fine TS-side). Compatible. |
| 10 | `urls.api.ts:24` | PATCH | `/v1/urls/{id}` | `PATCH /api/v1/urls/{url_id}` (`urls.py:124`) | **MISMATCH** — frontend `UpdateUrlRequest` allows `long_url` (`url.model.ts:29`); backend `URLUpdate` (`schemas/url.py:26`) does **not** accept `long_url`. Sending it → 422 / silently ignored. |
| 11 | `urls.api.ts:28` | DELETE | `/v1/urls/{id}` | `DELETE /api/v1/urls/{url_id}` (`urls.py:138`) — returns 204 no-content | **MISMATCH** — `ApiService.delete` tries to unwrap `{success,data}`; a 204 body is empty and `assertSuccess` will throw. |
| 12 | `urls.api.ts:33` | POST | `/v1/shorten` | none (no router at `/api/v1/shorten`) | **MISSING** — public/anonymous shorten endpoint not exposed. Landing page shortener broken. |
| 13 | `urls.api.ts:38` | GET | `/v1/urls/alias-check?alias=` | none | **MISSING** — alias availability check has no backend. |
| 14 | `analytics.api.ts:18` | GET | `/v1/analytics/overview` | none | **MISSING** — backend has `/api/v1/analytics/dashboard` (`analytics.py:85`) but contract returns `{clicks_30d, active_links_30d, uniques_30d}`, not `{total_links, total_clicks, clicks_this_week, active_links, top_referrers, weekly_timeseries}`. |
| 15 | `analytics.api.ts:22` | GET | `/v1/analytics/urls/{id}/timeseries?range=7d` | `GET /api/v1/analytics/{short_code}/timeseries` (`analytics.py:36`) | **MISMATCH** — (a) path segment `/urls/{id}` vs `/{short_code}` — 404; (b) query param: frontend sends `range=7d`, backend expects `since`/`until`/`bucket`; (c) response shape: frontend expects `{points:[{t,clicks}], granularity}` (`analytics.model.ts:6`), backend returns `{short_code, bucket, since, until, buckets:[{t,c}]}` (`schemas/analytics.py:26` + `analytics_service.py:67`). |
| 16 | `analytics.api.ts:26` | GET | `/v1/analytics/urls/{id}/geo?range=7d` | `GET /api/v1/analytics/{short_code}/geo` (`analytics.py:54`) | **MISMATCH** — (a) path segment `/urls/{id}` → 404; (b) frontend type `GeoBreakdown{country, country_code, clicks}` vs backend rows `{country, clicks}` (no `country_code`); (c) `range` param ignored. |
| 17 | `analytics.api.ts:30` | GET | `/v1/analytics/urls/{id}/referrers?range=7d` | `GET /api/v1/analytics/{short_code}/referrers` (`analytics.py:74`) | **MISMATCH** — (a) path 404; (b) field name: frontend `referer` (`analytics.model.ts:18`) vs backend `referrer` (`analytics_service.py:119`). |
| 18 | `analytics.api.ts:34` | GET | `/v1/analytics/urls/{id}/devices` | `GET /api/v1/analytics/{short_code}/devices` (`analytics.py:65`) | **MISMATCH** — (a) path 404; (b) frontend type `DeviceBreakdown{device, clicks}` vs backend `{device, os, browser, clicks}` (works by accidental subset match, but no aggregation — duplicate device rows). |
| 19 | `domains.api.ts:12` | GET | `/v1/domains` | `GET /api/v1/domains` (`domains.py:35`) | **MISMATCH** — response: frontend `DomainDto{host, verified, dns_token, created_at}` vs backend `DomainOut{domain, is_verified, verified_at, ssl_status, …}` (`schemas/domain.py:14`). Fields `host`, `verified`, `dns_token` all missing. Table renders blanks. |
| 20 | `domains.api.ts:16` | POST | `/v1/domains` with `{host}` | `POST /api/v1/domains` (`domains.py:22`) | **MISMATCH** — backend expects `{domain}` (`schemas/domain.py:10`), frontend sends `{host}` → 422. |
| 21 | `domains.api.ts:20` | POST | `/v1/domains/{id}/verify` | `POST /api/v1/domains/{domain_id}/verify` (`domains.py:65`) | **OK** (path match; response has same `DomainOut` mismatch as row 19). |
| 22 | `domains.api.ts:24` | DELETE | `/v1/domains/{id}` | 204 | **MISMATCH** — 204 unwrap issue (see row 11). |
| 23 | `api-keys.api.ts:12` | GET | `/v1/api-keys` | `GET /api/v1/api-keys` (`api_keys.py:52`) | **MISMATCH** — response: frontend `ApiKeyDto{prefix, …}` (`url.model.ts:44`) vs backend `ApiKeyOut{key_prefix, …}` (`schemas/api_key.py:17`). `prefix` column renders blank. |
| 24 | `api-keys.api.ts:16` | POST | `/v1/api-keys` | `POST /api/v1/api-keys` (`api_keys.py:22`) | **MISMATCH** — (a) create response: backend returns `ApiKeyCreated` with plaintext in field `key`; frontend reads `raw` (`api-keys.component.ts:116`, `url.model.ts:53`). Token panel never shows the key. (b) same `prefix` vs `key_prefix` mismatch in listing updates. |
| 25 | `api-keys.api.ts:20` | DELETE | `/v1/api-keys/{id}` | 204 | **MISMATCH** — 204 unwrap issue. |
| 26 | `webhooks.api.ts:12` | GET | `/v1/webhooks` | `GET /api/v1/webhooks` (`webhooks.py:39`) | **MISMATCH** — response: frontend `WebhookDto{url, events, is_active, secret_preview, created_at}` vs backend `WebhookOut{url, events, is_active, last_triggered, failure_count, created_at}` — `secret_preview` missing (display-only, minor). |
| 27 | `webhooks.api.ts:16` | POST | `/v1/webhooks` | `POST /api/v1/webhooks` (`webhooks.py:22`) | **OK** (backend `WebhookCreate` accepts `url` + `events`). |
| 28 | `webhooks.api.ts:20` | PATCH | `/v1/webhooks/{id}` | none | **MISSING** — update webhook not implemented; "toggle active" in frontend will 405/404. |
| 29 | `webhooks.api.ts:24` | DELETE | `/v1/webhooks/{id}` | 204 | **MISMATCH** — 204 unwrap issue. |
| 30 | `webhooks.api.ts:28` | POST | `/v1/webhooks/{id}/test` | none | **MISSING** — "Test" button in `webhooks.component.ts:155` always errors. |

### Endpoints backend exposes that frontend never calls

- `GET /api/v1/analytics/{short_code}/summary` (`analytics.py:24`)
- `GET /api/v1/analytics/dashboard` (`analytics.py:85`)
- `POST /api/v1/urls/bulk` (`urls.py:149`)
- `GET /api/v1/urls/{url_id}/qr` (`routers/qr.py:19`) — the frontend renders QR client-side via `qrcode` lib (`links/detail.component.ts:249`). Not a bug, but the server-side endpoint is dead code.
- `GET /api/v1/users/me/urls` (`users.py:38`)
- `GET /health`, `GET /ready`, `GET /metrics` — infra-only, expected.

---

## 2. Response-shape mismatches (summary)

| Entity | Frontend expects | Backend returns | Fields affected |
|---|---|---|---|
| `DomainOut` | `host, verified, dns_token` | `domain, is_verified, (no dns_token), ssl_status, verified_at` | host column, verified tag, dns_token copy-button |
| `ApiKeyOut` / `ApiKeyCreated` | `prefix`, plaintext in `raw` | `key_prefix`, plaintext in `key` | prefix column, "copy new key" panel |
| `WebhookOut` | `secret_preview` | `last_triggered, failure_count` (no `secret_preview`) | hidden secret preview display |
| Analytics `TimeseriesResponse` | `{points:[{t,clicks}], granularity}` | `{short_code, bucket, since, until, buckets:[{t,c}]}` | chart data completely empty |
| `GeoBreakdown` | `country, country_code, clicks` | `country, clicks` | no flag/sorting by code |
| `ReferrerBreakdown` | `referer, clicks` | `referrer, clicks` | *(one-letter typo — frontend has `referer`, RFC-correct; backend has `referrer`)* — top-referrers table blank |
| `DeviceBreakdown` | `device, clicks` | `device, os, browser, clicks` | duplicate "mobile/Chrome/Android" rows |
| `OverviewStats` | composite 6-field overview | not returned by any endpoint | whole Overview page blank |
| `URLOut` | `domain_id, click_count, last_clicked_at, is_active, expires_at, max_clicks, tags` | superset (adds `workspace_id, user_id, utm_*`) | **compatible** — extras ignored by TS |

Additional envelope concern — **204 responses through `ApiService.delete`**: `api.service.ts:60` does `.pipe(map((r) => unwrap(r)))`. A 204 body is empty (`null`), so `assertSuccess(null)` throws `"API request failed"`. Every delete (URL, domain, api-key, webhook) errors despite the backend succeeding.

---

## 3. Blocker fixes (exact patches)

Priority order = the things that must change to unbreak the Overview and the Link-detail analytics panels (the user's original 4 x 404s), plus collateral damage that blocks other pages.

### Blocker A — Analytics routes use `{short_code}`, frontend uses `{url_id}` (covers bugs 15–18 and row 17/18)

**Direction:** fix backend. The frontend contract (identify analytics by the URL's UUID, accept a simple `range` param, return the Overview-page struct) is reasonable and matches what every other resource uses. Rewrite `routers/analytics.py` to match.

**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\routers\analytics.py`

Replace the entire file content with the following (keep imports compatible — `analytics_service` helpers still take `short_code`, so we look that up first):

```python
"""Analytics router — matches admin-panel contract (range-based + url_id-based)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_ch, get_current_user, get_db
from app.models.user import User
from app.services import analytics_service, url_service

router = APIRouter()

Scope = Security(get_current_user, scopes=["analytics:read"])

Range = Literal["24h", "7d", "30d", "90d"]


def _range_to_since(range_: Range) -> tuple[date, str]:
    """Return (since, granularity) for a UI range."""
    today = date.today()
    if range_ == "24h":
        return today - timedelta(days=1), "hour"
    if range_ == "7d":
        return today - timedelta(days=7), "day"
    if range_ == "30d":
        return today - timedelta(days=30), "day"
    return today - timedelta(days=90), "day"


async def _resolve_short_code(db: AsyncSession, url_id: UUID, user_id: UUID) -> str:
    row = await url_service.get_url(db, url_id=url_id, user_id=user_id)
    return row.short_code


@router.get("/overview")
async def overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    user: Annotated[User, Scope] = ...,
):
    """Dashboard summary — total_links / clicks / this_week / active, plus top referrers and weekly series."""
    # URL counts from Postgres
    all_rows, total_links = await url_service.list_urls(
        db, user_id=user.id, workspace_id=None, offset=0, limit=10_000
    )
    active_links = sum(1 for r in all_rows if r.is_active)
    codes = [r.short_code for r in all_rows]

    # Click totals + weekly series from ClickHouse (best-effort; fall back to zeros)
    total_clicks = 0
    clicks_this_week = 0
    weekly_points: list[dict] = []
    top_referrers: list[dict] = []
    try:
        if codes:
            total_clicks, clicks_this_week, weekly_points, top_referrers = (
                await analytics_service.overview(ch, short_codes=codes)
            )
    except Exception:
        # ClickHouse down — still return Postgres-backed fields.
        pass

    return {
        "success": True,
        "data": {
            "total_links": total_links,
            "total_clicks": total_clicks,
            "clicks_this_week": clicks_this_week,
            "active_links": active_links,
            "top_referrers": top_referrers,
            "weekly_timeseries": weekly_points,
        },
    }


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
        ch, short_code=short_code, since=since, until=date.today(), bucket=granularity
    )
    # rows = [{"t": iso, "c": int}] → {"points": [{"t", "clicks"}], "granularity"}
    return {
        "success": True,
        "data": {
            "points": [{"t": r["t"], "clicks": r["c"]} for r in rows],
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
    short_code = await _resolve_short_code(db, url_id, user.id)
    rows = await analytics_service.geo(ch, short_code=short_code)
    # backend row: {"country", "clicks"} → add country_code (uppercased ISO-2 guess)
    out = [
        {
            "country": r["country"],
            "country_code": (r["country"][:2].upper() if r["country"] and r["country"] != "unknown" else "XX"),
            "clicks": r["clicks"],
        }
        for r in rows
    ]
    return {"success": True, "data": out}


@router.get("/urls/{url_id}/referrers")
async def referrers(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    range: Range = Query("7d"),
    user: Annotated[User, Scope] = ...,
):
    short_code = await _resolve_short_code(db, url_id, user.id)
    rows = await analytics_service.referrers(ch, short_code=short_code)
    # rename field: backend "referrer" → contract "referer"
    return {
        "success": True,
        "data": [{"referer": r["referrer"], "clicks": r["clicks"]} for r in rows],
    }


@router.get("/urls/{url_id}/devices")
async def devices(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ch=Depends(get_ch),
    range: Range = Query("7d"),
    user: Annotated[User, Scope] = ...,
):
    short_code = await _resolve_short_code(db, url_id, user.id)
    rows = await analytics_service.devices(ch, short_code=short_code)
    # aggregate to {device, clicks}
    agg: dict[str, int] = {}
    for r in rows:
        agg[r["device"]] = agg.get(r["device"], 0) + int(r["clicks"])
    return {
        "success": True,
        "data": [{"device": d, "clicks": c} for d, c in sorted(agg.items(), key=lambda x: -x[1])],
    }
```

**Supporting change** — add `overview()` helper to `analytics_service`:

**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\services\analytics_service.py`

Append at end of file:

```python
async def overview(
    ch: AsyncClient, *, short_codes: list[str]
) -> tuple[int, int, list[dict], list[dict]]:
    """Aggregate overview for a user's links: (total_clicks, clicks_last_7d, weekly_series, top_referrers)."""
    if not short_codes:
        return 0, 0, [], []
    codes_lit = ",".join(f"'{c}'" for c in short_codes)  # codes are [A-Za-z0-9_-], safe
    # total clicks (all time)
    total_rows = await _rows(
        ch,
        f"SELECT count() FROM clicks WHERE short_code IN ({codes_lit})",
    )
    total_clicks = int(total_rows[0][0]) if total_rows else 0
    # last 7 days
    week_rows = await _rows(
        ch,
        f"SELECT count() FROM clicks WHERE short_code IN ({codes_lit}) AND ts >= today() - 7",
    )
    clicks_this_week = int(week_rows[0][0]) if week_rows else 0
    # weekly timeseries (day buckets)
    series_rows = await _rows(
        ch,
        f"""
        SELECT toDate(ts) AS t, count() AS c
          FROM clicks
         WHERE short_code IN ({codes_lit}) AND ts >= today() - 7
         GROUP BY t ORDER BY t
        """,
    )
    weekly_points = [
        {"t": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]), "clicks": int(r[1])}
        for r in series_rows
    ]
    # top referrers
    ref_rows = await _rows(
        ch,
        f"""
        SELECT referrer_domain, count() AS c
          FROM clicks
         WHERE short_code IN ({codes_lit}) AND ts >= today() - 30
         GROUP BY referrer_domain ORDER BY c DESC LIMIT 5
        """,
    )
    top_referrers = [{"referer": r[0] or "direct", "clicks": int(r[1])} for r in ref_rows]
    return total_clicks, clicks_this_week, weekly_points, top_referrers
```

### Blocker B — `ApiService.delete` breaks on 204 No Content (rows 11, 22, 25, 29)

**Direction:** fix frontend. Backend correctly returns 204 per HTTP spec.

**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\api\api.service.ts`

Change line 59-61:

```ts
  delete<T = void>(path: string): Observable<T> {
    return this.http.delete<ApiResponse<T> | null>(path).pipe(
      map((r) => (r == null ? (undefined as unknown as T) : unwrap(r))),
    );
  }
```

### Blocker C — `domains.api.ts` field names don't match backend `DomainOut` (rows 19, 20, 21)

**Direction:** fix frontend — the backend schema name `domain`/`is_verified` is the persisted column name; renaming backend is more churn. Update the TS type and call sites.

**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\models\url.model.ts` lines 36-42:

```ts
export interface DomainDto {
  id: string;
  domain: string;                 // was: host
  is_verified: boolean;           // was: verified
  verified_at: string | null;
  ssl_status: string;
  created_at: string;
}
```

**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\api\domains.api.ts` line 15-17:

```ts
  create(domain: string): Observable<DomainDto> {
    return this.api.post<DomainDto>('/v1/domains', { domain });
  }
```

**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\domains\domains.component.ts`

- Line 65: `{{ d.host }}` → `{{ d.domain }}`
- Lines 67-68: `@if (d.verified)` → `@if (d.is_verified)`; update the `updated.verified` reference on line 144-145 to `updated.is_verified`.
- Remove the DNS token column (lines 58, 70-73) — backend doesn't expose one. Add a "Verified" timestamp column showing `d.verified_at | shortDate` instead, or just drop the column.

### Blocker D — API-key `prefix` → `key_prefix`, `raw` → `key` (rows 23, 24)

**Direction:** fix frontend.

**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\models\url.model.ts` lines 44-54:

```ts
export interface ApiKeyDto {
  id: string;
  name: string;
  key_prefix: string;          // was: prefix
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
  is_active: boolean;
  /** Only present on creation response — shown to user once. */
  key?: string;                // was: raw
}
```

**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\api-keys\api-keys.component.ts`

- Line 56: `{{ k.prefix }}…` → `{{ k.key_prefix }}…`
- Line 116: `{{ created()?.raw }}` → `{{ created()?.key }}`
- Line 117: `[value]="created()?.raw ?? ''"` → `[value]="created()?.key ?? ''"`

### Blocker E — Missing public `POST /api/v1/shorten` (row 12)

**Direction:** fix backend — add the anonymous-shorten endpoint. The landing page depends on it.

**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\routers\urls.py`

Add (after existing routes, e.g. after line 175). Also adjust `main.py` to expose a `/shorten` mount.

Append to `urls.py`:

```python
from fastapi import Request
from pydantic import BaseModel


class ShortenIn(BaseModel):
    long_url: str


@router.post("/public/shorten")
async def public_shorten(
    body: ShortenIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
):
    """Anonymous (no auth) short-link creation — landing page."""
    await is_safe(body.long_url)
    row = await url_service.create_url(
        db, cache, user_id=None, workspace_id=None,
        body=URLCreate(long_url=body.long_url),
    )
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    return {
        "success": True,
        "data": {
            "short_code": row.short_code,
            "short_url": f"{scheme}://{host}/{row.short_code}",
        },
    }
```

Then mount a second router in `main.py` around line 87 so `POST /api/v1/shorten` resolves:

**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\main.py` — insert after line 87:

```python
    # Alias: public anonymous /api/v1/shorten → /api/v1/urls/public/shorten
    from fastapi import APIRouter
    shorten_alias = APIRouter()

    @shorten_alias.post("/shorten")
    async def shorten_alias_ep(body: dict, request: "Request"):  # type: ignore
        from app.routers.urls import public_shorten, ShortenIn
        # delegate — FastAPI will recreate deps via Depends in the inner call
        return await public_shorten(ShortenIn(**body), request,
                                    *(await _resolve_deps_for_shorten()))  # see note

    app.include_router(shorten_alias, prefix="/api/v1", tags=["public"])
```

*Simpler alternative* (recommended) — just mount `urls.router` a second time with path `/api/v1` and add a route `@router.post("/shorten")` at module scope instead of `/public/shorten`:

Add to `urls.py`:

```python
public_router = APIRouter()

@public_router.post("/shorten")
async def public_shorten(
    body: ShortenIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
):
    ...
```

And in `main.py` line 88:

```python
    app.include_router(urls.public_router, prefix="/api/v1", tags=["public"])
```

Also update auth interceptor anonymous list to `/v1/shorten` (already there: `auth.interceptor.ts:6`) — OK.

### Blocker F — Missing `GET /api/v1/urls/alias-check` (row 13)

**Direction:** fix backend — cheap route, simple contract.

**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\routers\urls.py` — add near the bottom:

```python
@router.get("/alias-check")
async def alias_check(
    alias: str = Query(..., min_length=3, max_length=10, pattern=r"^[A-Za-z0-9_-]+$"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
):
    taken = await url_service.slug_exists(db, slug=alias)
    return {"success": True, "data": {"available": not taken}}
```

(Ensure `url_service.slug_exists` exists or add the trivial SELECT.) **Important:** declare this route **before** `GET /{url_id}` in the file (FastAPI resolves in order, otherwise `"alias-check"` will match the UUID path). Looking at `urls.py`, `/{url_id}` is at line 112 — insert `alias-check` *before* that (or use a distinct prefix like `/check-alias`, same route on FE side).

### Blocker G — Frontend sends `email` in `PATCH /users/me`; backend doesn't accept (row 5)

**Direction:** two options. Since changing email is a security-sensitive operation normally behind verification, drop the field frontend-side for now.

**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\settings\settings.component.ts` line 101:

```ts
          { full_name: this.profileForm.getRawValue().name },
```

(And remove the email input or make it `readonly`.)

### Blocker H — Logout: backend requires `LogoutIn.refresh_token`, frontend sends `{}` (row 4)

**Direction:** fix backend — make `refresh_token` optional so both raw-bearer-only logout and refresh-token-revoke logout work. The schema already has `refresh_token: str | None = None`, so actual behavior is: FastAPI still parses `{}` fine (pydantic accepts `{}` because field is optional). **Re-verify:** `schemas/auth.py:22` is `refresh_token: str | None = None` — frontend `{}` body is valid. **False alarm — OK.**

But actual bug: frontend `auth.api.ts:29` sends `POST` with no body → `this.api.post<void>('/v1/auth/logout')` defaults to `body ?? {}` → `{}` → parses fine. However `auth.service.ts:167` also sends `{}`. Both fine. **Mark row 4 as OK** on re-read.

### Blocker I — Settings password endpoint missing (row 6)

**Direction:** either implement the backend endpoint or disable the UI. Given other pages work, likely out-of-scope for "unblock the dashboard". Minimum fix: remove the form OR stub backend.

**File (frontend, disable):** `admin-panel/src/app/features/settings/settings.component.ts` lines 46-67 — comment out the password form, and the `changePassword()` method on 113-125.

**File (backend stub, preferred):** add to `api-service/app/routers/auth.py`:

```python
class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/password")  # POST /api/v1/auth/password
async def change_password(
    body: PasswordChangeIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Security(get_current_user, scopes=["urls:write"])] = ...,
):
    await auth_service.change_password(
        db, user=user, current=body.current_password, new=body.new_password,
    )
    return {"success": True, "data": {"changed": True}}
```

And fix the frontend path — currently `/auth/password` (missing `/v1` prefix):

**File:** `admin-panel/src/app/features/settings/settings.component.ts:117`:

```ts
      await firstValueFrom(this.api.post<void>('/v1/auth/password', this.passwordForm.getRawValue()));
```

### Blocker J — Missing `PATCH /api/v1/webhooks/{id}` and `POST /api/v1/webhooks/{id}/test` (rows 28, 30)

**Direction:** fix backend — frontend already wires buttons for these.

**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\routers\webhooks.py` — add:

```python
from app.schemas.webhook import WebhookUpdate  # new — add to schemas/webhook.py


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: UUID,
    body: WebhookUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    row = await webhook_service.update_webhook(
        db, workspace_id=workspace.id, webhook_id=webhook_id,
        url=str(body.url) if body.url else None,
        events=body.events, is_active=body.is_active,
    )
    return {"success": True, "data": WebhookOut.model_validate(row)}


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    workspace: Annotated[Workspace, Depends(get_current_workspace)],
    user: Annotated[User, WriteScope] = ...,
):
    ok = await webhook_service.deliver_test(db, workspace_id=workspace.id, webhook_id=webhook_id)
    return {"success": True, "data": {"ok": ok}}
```

And in `schemas/webhook.py`:

```python
class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None
```

(Add corresponding `update_webhook` / `deliver_test` helpers in `services/webhook_service.py`.)

### Blocker K — `UrlDto` / `UpdateUrlRequest` mismatches (rows 9, 10)

**Direction:** fix frontend — backend schema is source of truth for writes.

**File:** `admin-panel/src/app/core/models/url.model.ts`

- Remove `long_url?` from `UpdateUrlRequest` (line 29) — backend doesn't accept it.
- Optional: add `utm_source`, `utm_medium`, `utm_campaign`, `password`, `max_clicks`, `custom_slug` to `CreateUrlRequest` for parity (already mostly there; `custom_slug` is there).

### Blocker L — Referrer field name `referer` vs `referrer` (row 17)

Handled inside Blocker A — the new router maps `referrer` → `referer` in response.

### Blocker M — Geo `country_code` missing (row 16)

Handled inside Blocker A — synthesises a two-letter code (best-effort; long-term the worker should persist an actual ISO-3166 code in ClickHouse).

---

## 4. Recommendations (non-blocker, but fragile)

1. **Single source of truth for DTOs.** Generate the TS models from the FastAPI OpenAPI schema (`openapi-typescript` or `orval`). Seven of the thirty rows above are pure name-drift (`host` vs `domain`, `prefix` vs `key_prefix`, `raw` vs `key`, `referer` vs `referrer`). This is systematic, not random.

2. **Add a contract smoke test.** A pytest that hits every route in the OpenAPI schema with a real `TestClient` and asserts the JSON matches the admin-panel interface shapes (parse via dataclasses generated from the `.ts` models, or hand-rolled). Would catch every issue above on CI.

3. **Analytics identity.** Backend keys analytics on `short_code`; frontend on `url_id`. Pick one — `short_code` is the better key (shorter, human-readable, matches the redirect service's primary key in ClickHouse and Redis). If you keep `url_id` at the edge, the lookup in Postgres on every analytics call is wasted I/O. Consider caching `url_id → short_code` in the cache Redis.

4. **Response envelope uniformity.** Most endpoints return `{success:true, data:...}` explicitly via dict literals. Three return 204 (delete). One returns a raw binary (`qr.py:31`). Standardise: either *always* envelope + 200, or have the interceptor tolerate empty-body 204 plus raw-binary responses. The current `ApiService` breaks on both.

5. **Auth interceptor anon-list uses substring match** (`auth.interceptor.ts:9` — `url.includes(p)`). A user-supplied URL containing the substring `/auth/login` could accidentally bypass auth. Use exact-path match against the post-baseUrl pathname.

6. **`DELETE /urls/{id}` returns 204 while `DELETE /webhooks/{id}` does the same** — consistent. But `POST /auth/logout` returns `{success:true, data:{logged_out:true}}` with status 200 (`auth.py:120`). Pick one convention for no-content writes.

7. **Scopes inconsistency.** `api_keys.py:17` uses `["urls:write"]`/`["urls:read"]` for *API-key management*; webhooks, domains do the same. That's overloading — compromising a URL-scoped token lets you mint new keys. Define `api_keys:write`, `webhooks:write`, etc.

8. **Frontend's `shortenPublic`** is hard-wired to `/v1/shorten`, but the auth-interceptor anon list says `/v1/shorten` (`auth.interceptor.ts:6`). If/when you implement Blocker E, make sure the path matches exactly (including absence of trailing slash).

9. **Dashboard doesn't consume `GET /api/v1/analytics/dashboard`.** The workspace-level dashboard endpoint returns `clicks_30d/active_links_30d/uniques_30d` but nobody calls it. Either delete it or wire it into the overview alongside the new `/overview`.

10. **QR code duplication.** `routers/qr.py` exists but the frontend renders QR client-side via the `qrcode` npm package (`detail.component.ts:249`). Pick one: if server-side, reduce JS bundle; if client-side, drop `qr.py`. Keeping both is two code paths to maintain.

---

## Appendix — all frontend call sites (non-core)

Covered by audit (grep `this.(api|http).`):

- `features/api-keys/api-keys.component.ts:149,170,193` — list/create/revoke (via `ApiKeysApi`).
- `features/webhooks/webhooks.component.ts:127,141,155,173` — list/create/test/delete (via `WebhooksApi`).
- `features/landing/landing.component.ts:116` — `shortenPublic` (via `UrlsApi`).
- `features/settings/settings.component.ts:99,117` — PATCH `/v1/users/me`, POST `/auth/password`.
- `features/domains/domains.component.ts:116,128,141,160` — list/create/verify/delete (via `DomainsApi`).
- `features/links/links.store.ts:61,74,81,87` — list/create/update/delete (via `UrlsApi`).
- `features/links/detail.component.ts:214,228,232,236` — get url + 3x analytics.
- `features/dashboard/overview.component.ts:112` — `analytics.overview()`.
- `core/auth/auth.service.ts:67,86,104,142,167` — direct `HttpClient` calls to `/v1/users/me`, `/v1/auth/{login,register,refresh,logout}`.

No other `this.http` or `this.api` consumers exist outside these files.
