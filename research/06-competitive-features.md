# 06 - Competitive Feature Matrix & Roadmap Recommendations

**Date:** 2026-04-14
**Agent:** RESEARCH-COMP
**Scope:** Feature landscape of leading URL shortener / link management platforms
as of Q2 2026, benchmarked against our current product.

---

## 0. Executive Summary

Our product is already competitive on the **core link-level capabilities** (custom
alias, password, expiration, tags, UTM, QR, webhooks, custom domains, click
tracking with GeoIP/UA/bot detection, ClickHouse-backed analytics, JWT + API keys,
workspaces with RBAC, rate limiting by plan). Compared to the 2026 market, the
most visible gaps are:

1. **Smart routing at redirect time** — A/B split, device targeting (iOS/Android),
   geo targeting, deep links. Every serious competitor has these; our redirect
   hot path currently only does password/expiry/max-clicks checks.
2. **Link-in-bio pages** — Dub, t.ly (OneLinks), Cuttly, Bitly all ship this now.
   It is the single most-requested growth feature for creators.
3. **Retargeting pixel injection** — FB / GA / TikTok / LinkedIn pixel auto-fire
   through an interstitial. Differentiates Rebrandly, RocketLink, Replug, LinkSplit.
4. **Branded QR codes** (logo, color, frame) — we only emit plain PNG/SVG.
5. **Folders** (in addition to tags) — Dub shipped this in 2025; mental model is
   distinct from tags (1:N vs N:M) and users expect both.
6. **Enterprise identity** — SAML SSO, SCIM provisioning, audit log. Bitly, Dub,
   Rebrandly all have SAML; SCIM is rarer and a clear upsell.
7. **Safety pipeline** — real-time phishing/malware scanning (Google Web Risk or
   equivalent) plus a preview interstitial. Bitly's three-pronged trust system
   is table stakes for any platform that wants Fortune-500 customers.
8. **Bulk ops** — CSV import/export, bulk edit, bulk tag. Short.io and Rebrandly
   compete hard on this.
9. **Chrome extension** + **iOS/Android share sheet** — the #1 daily UX driver
   for power users.
10. **Conversion tracking** — Dub's marquee differentiator. Stripe/Shopify hooks
    that tie a click to a signup or revenue event.

Detailed matrix, prioritized top-10, and architecture notes follow.

---

## 1. Competitor One-Line Summary

| Platform | Positioning (2026) | Top differentiators |
|---|---|---|
| **bit.ly** | Market leader, Fortune-500 focus | AI analytics (Bitly Assist + Weekly Insights), Connection Layer (links+QR+pages), SAML+SCIM, Web Risk integration, Shopify, MCP server |
| **dub.sh (dub.co)** | Modern OSS-friendly, developer-first | Conversion tracking (Stripe/Shopify), A/B test, link cloaking, custom link previews (OG), folders+tags+UTM templates, Raycast, AGPLv3 self-host |
| **short.io** | Branded-domain specialist, fair pricing | Multi-domain mgmt, deep links (iOS scheme + Android package), A/B, geo/device redirect, bulk CSV, team roles |
| **cutt.ly** | Deep analytics for marketers | Hourly heat maps, campaign aggregation, link-in-bio, QR w/ logo, interactive surveys, per-tag geo comparison |
| **rebrandly** | Enterprise branding | 100k+ links/sec bulk, retargeting scripts, deep linking, AI publish-time recommendation, SOC2+HIPAA, dedicated infra |
| **t.ly** | Simple, cheap, "world's shortest" | OneLinks (link-in-bio), A/B rotation, webhooks, Smart Links (geo/device/browser routing), Chrome ext, Google Workspace |
| **kutt.it** | OSS self-host, minimal | OIDC login, custom HTML themes, Docker/SQLite default, API |
| **tinyurl** | Classic, brand recognition | Branded domains on Pro, Analytics Dashboard, QR (Pro+), bulk API |
| **yourls** | OSS self-host, plugin ecosystem | PHP+MySQL, plugin system (Open Graph, password, GA tags, OIDC), bookmarklet |

---

## 2. Feature Matrix

Tick = "shipped and generally available on at least one paid tier".
`~` = partial / indirect (e.g. via plugin, requires workaround).
`-` = not supported.
"**Us**" column reflects the state described in the task prompt.

### 2.1 Link-level features

| # | Feature | bit.ly | dub | short.io | cuttly | rebrandly | t.ly | kutt | tinyurl | yourls | **Us** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 | Custom alias / vanity slug | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Password protection | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | ~ (plugin) | ✓ |
| 3 | Expiration (date / max clicks) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ~ | ✓ |
| 4 | UTM parameters (stored) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ~ | ~ | ✓ |
| 5 | UTM builder UI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | - | - | - |
| 6 | UTM templates (reusable) | ✓ | ✓ | - | ✓ | ✓ | - | - | - | - | - |
| 7 | A/B split routing | - | ✓ | ✓ | - | ~ | ✓ | - | - | - | - |
| 8 | Device targeting (iOS/Android) | ✓ | ✓ | ✓ | ~ | ✓ | ✓ | - | - | - | - |
| 9 | Geo targeting (redirect by country) | ✓ | ✓ | ✓ | ~ | ✓ | ✓ | - | - | - | - |
| 10 | Mobile deep links (scheme/intent) | ✓ | ✓ | ✓ | - | ✓ | ✓ | - | - | - | - |
| 11 | Link cloaking (masked) | - | ✓ | ✓ | ~ | ✓ | - | - | - | - | - |
| 12 | Retargeting pixel injection | ~ | - | ~ | ~ | ✓ | - | - | - | - | - |
| 13 | Custom OG preview (title/image) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | - | ~ (plugin) | - |
| 14 | Preview / click-to-confirm page | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| 15 | Email-gated links | ✓ | - | ✓ | - | ✓ | - | - | - | - | - |
| 16 | QR code (basic PNG/SVG) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (plugin) | ✓ |
| 17 | Branded QR (logo, color, frame) | ✓ | ~ | ✓ | ✓ | ✓ | ✓ | - | - | - | - |
| 18 | Dynamic QR (destination editable) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 19 | Link-in-bio page | ✓ | ~ | - | ✓ | ✓ | - | - | - | - | - |
| 20 | Smart link (rule chain) | ✓ | ✓ | ✓ | ~ | ✓ | ✓ | - | - | - | - |

### 2.2 Organization / collaboration

| # | Feature | bit.ly | dub | short.io | cuttly | rebrandly | t.ly | kutt | tinyurl | yourls | **Us** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 21 | Workspaces / teams | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ~ | - | ✓ |
| 22 | Workspace switcher UI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | - | - | - (not wired) |
| 23 | Role-based access (owner/admin/editor/viewer) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ~ | - | ✓ |
| 24 | Folders / collections | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | - | - | ~ | - |
| 25 | Tags | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | - | ~ | ✓ |
| 26 | Colored tags | ✓ | ✓ | - | ✓ | ✓ | - | - | - | - | - |
| 27 | Bulk CSV import | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | ~ | - |
| 28 | Bulk CSV export | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | ✓ | - |
| 29 | Bulk edit / bulk tag | ✓ | ✓ | ✓ | ✓ | ✓ | - | - | - | - | - |
| 30 | Comments / mentions on links | ✓ | ✓ | - | - | ✓ | - | - | - | - | - |
| 31 | Activity log (per-link) | ✓ | ✓ | ✓ | - | ✓ | - | - | - | - | - |
| 32 | Approval workflow | ✓ | - | - | - | ✓ | - | - | - | - | - |

### 2.3 Analytics

| # | Feature | bit.ly | dub | short.io | cuttly | rebrandly | t.ly | kutt | tinyurl | yourls | **Us** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 33 | Click counts + timeseries | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 34 | Geo breakdown | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | ✓ | ✓ | ✓ |
| 35 | Device / browser / OS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | ✓ | ✓ | ✓ |
| 36 | Referrer breakdown | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | ✓ | ✓ |
| 37 | Unique visitors | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | - | - |
| 38 | Bot vs human split | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | - | ✓ (detect only) |
| 39 | Hourly heat map | - | - | - | ✓ | ~ | - | - | - | - | - |
| 40 | Real-time stream | ✓ | ✓ | - | ~ | ✓ | - | - | - | - | - |
| 41 | Conversion / revenue tracking | - | ✓ | - | - | - | - | - | - | - | - |
| 42 | Funnels / cohort | ✓ | ~ | - | - | ~ | - | - | - | - | - |
| 43 | Scheduled / email reports | ✓ | - | ✓ | ✓ | ✓ | - | - | - | - | - |
| 44 | Alerts on click spikes | ✓ | - | - | ~ | ✓ | - | - | - | - | - |
| 45 | Public shareable report links | ✓ | ✓ | ✓ | - | ✓ | - | - | - | - | - |
| 46 | UTM-grouped analytics | ✓ | ✓ | ~ | ✓ | ✓ | ~ | - | - | - | ~ |
| 47 | AI insights / anomaly detection | ✓ (Assist) | - | - | - | ✓ | - | - | - | - | - |

### 2.4 Integrations

| # | Feature | bit.ly | dub | short.io | cuttly | rebrandly | t.ly | kutt | tinyurl | yourls | **Us** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 48 | Zapier / Make | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | ~ | - |
| 49 | Slack notifications | ✓ | ✓ | ✓ | - | ✓ | - | - | - | - | - (webhooks only) |
| 50 | Discord webhooks | - | ✓ | ~ | - | - | - | - | - | - | - |
| 51 | GA / GTM auto-inject | ✓ | - | ~ | ✓ | ✓ | - | - | - | ✓ (plugin) | - |
| 52 | FB Pixel auto-inject | ~ | - | ~ | ✓ | ✓ | - | - | - | - | - |
| 53 | Chrome extension | ✓ | ~ | ✓ | ✓ | ✓ | ✓ | - | ✓ | - | - |
| 54 | Share sheet (iOS / Android) | ✓ | - | ✓ | ✓ | ✓ | - | - | ✓ | - | - |
| 55 | WordPress plugin | ✓ | - | - | ✓ | ✓ | - | - | - | - | - |
| 56 | HubSpot / Salesforce | ✓ | - | - | - | ✓ | - | - | - | - | - |
| 57 | Shopify | ✓ | ✓ | - | - | ~ | - | - | - | - | - |
| 58 | Stripe (revenue attr.) | - | ✓ | - | - | - | - | - | - | - | - |
| 59 | Raycast / CLI | - | ✓ | - | - | - | - | - | - | - | - |
| 60 | MCP server (AI agents) | ✓ | ~ | - | - | - | - | - | - | - | - |

### 2.5 Admin / platform

| # | Feature | bit.ly | dub | short.io | cuttly | rebrandly | t.ly | kutt | tinyurl | yourls | **Us** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 61 | SAML / OIDC SSO | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ (OIDC) | - | ~ | - |
| 62 | SCIM provisioning | ✓ (1.1+2.0) | ✓ | ~ | - | ✓ | - | - | - | - | - |
| 63 | Audit log | ✓ | ✓ | ~ | - | ✓ | - | - | - | - | - |
| 64 | 2FA / TOTP | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | ~ | ~ | - |
| 65 | IP allow-list | ✓ | - | - | - | ✓ | - | - | - | - | - |
| 66 | API rate-limit headers (X-RateLimit-*) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | - | ~ |
| 67 | OpenAPI / Swagger spec | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | ~ | ~ | ✓ |
| 68 | Typed SDK (TS / Py / Go) | ✓ | ✓ (TS+Py+Go) | ~ | ~ | ✓ | ~ | - | ~ | - | - |
| 69 | Per-plan usage quotas visible in UI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | - | ~ |
| 70 | Stripe billing + invoices | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | ✓ | - | - |

### 2.6 Safety / abuse

| # | Feature | bit.ly | dub | short.io | cuttly | rebrandly | t.ly | kutt | tinyurl | yourls | **Us** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 71 | Phishing / malware real-time scan | ✓ (Web Risk) | ~ | ~ | ~ | ✓ | ~ | - | ~ | - | - |
| 72 | Domain blocklist (bulk manage) | ✓ | - | ~ | ~ | ✓ | - | - | - | - | - |
| 73 | Manual review queue for abuse | ✓ | - | - | - | ✓ | - | - | - | - | - |
| 74 | Interstitial warning on flagged URL | ✓ | - | - | - | ✓ | - | - | - | - | - |
| 75 | CAPTCHA on anonymous create | ✓ | - | ~ | ~ | - | ~ | - | ~ | - | - |
| 76 | Auto-expire for anonymous links | - | - | - | ~ | - | - | - | - | - | - |

### 2.7 UX

| # | Feature | bit.ly | dub | short.io | cuttly | rebrandly | t.ly | kutt | tinyurl | yourls | **Us** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 77 | Dark mode | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | ? |
| 78 | Keyboard shortcuts | ✓ | ✓ | - | - | - | - | - | - | - | - |
| 79 | Favicon preview on link card | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | - | - | - |
| 80 | OG image preview on link card | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - | - | - | - |
| 81 | Mobile app (iOS/Android) | ✓ | - | ~ | ~ | ✓ | - | - | - | - | - |
| 82 | Drag-to-reorder / list views | ✓ | ✓ | ✓ | ✓ | ✓ | - | - | - | - | - |

**Totals (rows where we have it):** 14/82 ticks on our side vs ~70-75/82 for
Bitly, ~55/82 for Dub, ~50/82 for Short.io. We are roughly at Kutt.it parity on
core but already ahead on analytics stack and tags/UTM storage; we are a full
tier behind on smart routing, bio pages, retargeting, safety, integrations,
and enterprise identity.

---

## 3. Top 10 Features to Implement NOW (P0)

Ranked by (user-value × request-frequency) / engineering-effort. Each entry
covers the user promise, data-model delta, API surface, UI work, and a rough
effort band.

### P0-1. Smart routing: device + geo + A/B (unified rules engine)

**One-liner.** Every competitor has "if iOS then X, else if Android then Y,
else Z" and "A/B 50/50 between two URLs". Build this once, as a JSON rule
engine evaluated in the redirect hot path.

**Data model.**
```sql
ALTER TABLE links ADD COLUMN routing_rules JSONB;
-- Shape: { "ab": [{"url": "...", "weight": 50}, ...],
--          "device": {"ios": "...", "android": "...", "desktop": "..."},
--          "geo": {"US": "...", "DE": "...", "default": "..."} }
-- Evaluation order: geo -> device -> ab -> fallback to links.long_url
```
Add `link_route_hits` ClickHouse column: `route_branch LowCardinality(String)`
so analytics can compare variants.

**API.**
- `POST /v1/links` accepts `routing_rules` (validated: weights sum to 100, URLs
  reachable, max 10 geo entries).
- `GET /v1/links/{id}/ab-stats` returns per-branch CTR.

**Redirect-service.** Currently the hot path is `SELECT link WHERE slug=... ->
check password/expiry -> 302`. Add one function `resolveDestination(link, req)`
that consults `routing_rules`. Keep the rule JSON denormalized on the Redis
cache row so we avoid a second roundtrip. Expected +80-150 microseconds.

**UI.** New "Routing" tab on the link edit drawer with three sub-panels
(Geo / Device / A-B). Use a JSON schema form to keep it tight.

**Effort:** **L** (≈ 5-7 dev-days). Hot path change => careful load test.

### P0-2. Branded QR codes (logo + color + frame)

**One-liner.** Let users drop their logo into the QR center and pick brand
colors. Bitly, Short.io, Cuttly all do this; our PNG/SVG emitter already exists
so this is mostly an options pass-through.

**Data model.**
```sql
ALTER TABLE links ADD COLUMN qr_style JSONB;
-- { "fg": "#111", "bg": "#fff", "logo_url": "...", "frame": "rounded",
--   "dots": "rounded", "corner_style": "extra-rounded" }
```

**API.** Extend `GET /v1/links/{id}/qr?size=&fmt=` with style query params and a
`POST /v1/links/{id}/qr-style` to persist defaults. Validate hex colors and
minimum contrast ratio (>= 3:1) to keep scans reliable.

**UI.** QR modal grows a sidebar: color pickers, logo upload (S3 via presigned
URL), live preview. Use `qr-code-styling` (MIT) on the client for preview,
server still renders the canonical PNG/SVG.

**Effort:** **M** (≈ 2-3 dev-days).

### P0-3. Folders (alongside existing tags)

**One-liner.** Tags are N:M and flat; folders are 1:N and hierarchical. Users
want both. Dub shipped this mid-2025 and saw immediate retention lift.

**Data model.**
```sql
CREATE TABLE folders (
  id UUID PRIMARY KEY,
  workspace_id UUID NOT NULL,
  parent_id UUID NULL REFERENCES folders(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  color TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE links ADD COLUMN folder_id UUID REFERENCES folders(id);
CREATE INDEX idx_links_folder ON links(workspace_id, folder_id);
```

**API.**
- `GET/POST/PATCH/DELETE /v1/folders`
- `PATCH /v1/links/{id}` accepts `folder_id`
- `POST /v1/links/bulk-move { ids: [...], folder_id }`

**UI.** Left sidebar tree, drag-drop, breadcrumb in list header. Folder-level
aggregated analytics (Dub does this — users love it).

**Effort:** **M** (≈ 3 dev-days).

### P0-4. Bulk CSV import / export + bulk edit

**One-liner.** Migration on-ramp from Bitly/Rebrandly. A clear blocker for any
customer with >500 existing links. Also serves as export for GDPR.

**Data model.** No schema change; add `bulk_jobs` table for async progress
tracking.
```sql
CREATE TABLE bulk_jobs (
  id UUID PRIMARY KEY, workspace_id UUID, kind TEXT,
  status TEXT, total INT, done INT, failed INT,
  result_url TEXT, created_at TIMESTAMPTZ, finished_at TIMESTAMPTZ
);
```

**API.**
- `POST /v1/links/import` (multipart CSV, returns job id)
- `GET /v1/bulk-jobs/{id}` polls progress
- `POST /v1/links/export` (filter json) -> async CSV in S3 signed URL
- `POST /v1/links/bulk-patch { ids, patch }` (tag, folder, expires_at)

**UI.** "Import" button on list page -> wizard (upload, column-map, preview,
commit). Checkbox multi-select + bulk toolbar.

**Effort:** **M** (≈ 3-4 dev-days, mostly column-mapping UX and dedupe rules).

### P0-5. Link preview page + favicon/OG on link cards

**One-liner.** Two related wins: (a) safety interstitial ("You are about to
visit example.com — continue?") which is expected UX on shared links, and
(b) small preview thumbnails on the link list make the UI feel premium.

**Data model.**
```sql
ALTER TABLE links ADD COLUMN preview_enabled BOOLEAN DEFAULT false;
ALTER TABLE links ADD COLUMN og_title TEXT, ADD COLUMN og_description TEXT,
  ADD COLUMN og_image_url TEXT, ADD COLUMN favicon_url TEXT,
  ADD COLUMN og_fetched_at TIMESTAMPTZ;
```

**API.**
- Background worker fetches OG tags on link create / update (respect robots,
  5 s timeout, max 2 MB). Cache favicon via `https://icons.duckduckgo.com/ip3/`
  as a fallback.
- `GET /preview/{slug}` serves an HTML interstitial with continue button.

**UI.** Toggle on link form. Cards on the list page show favicon + OG image
with graceful fallback.

**Effort:** **M** (≈ 2 dev-days). Watch out for SSRF — restrict fetch to public
IPs only, no 10.0.0.0/8 or 169.254.0.0/16.

### P0-6. UTM builder UI + UTM templates

**One-liner.** We already store UTMs; add a first-class "build UTM, save as
template, reuse across campaigns" flow. Dub made this a headline feature in
its 2025 sidebar redesign.

**Data model.**
```sql
CREATE TABLE utm_templates (
  id UUID PRIMARY KEY, workspace_id UUID, name TEXT,
  utm_source TEXT, utm_medium TEXT, utm_campaign TEXT,
  utm_term TEXT, utm_content TEXT, created_by UUID,
  created_at TIMESTAMPTZ
);
```

**API.** `GET/POST/PATCH/DELETE /v1/utm-templates`.

**UI.** Inline form on the link-create drawer with "Save as template" and a
dropdown of existing templates. Query-string preview updates live.

**Effort:** **S** (≈ 1 dev-day).

### P0-7. Retargeting pixel injection via interstitial

**One-liner.** User configures "fire FB Pixel / GA / LinkedIn / TikTok pixel X"
on this link; we redirect via a sub-100 ms HTML page that fires the pixel, then
window.location.replace to destination. Rebrandly, Replug, LinkSplit monetize
this heavily.

**Data model.**
```sql
CREATE TABLE retarget_pixels (
  id UUID PRIMARY KEY, workspace_id UUID,
  kind TEXT, -- 'fb', 'ga4', 'linkedin', 'tiktok', 'pinterest', 'twitter'
  pixel_id TEXT, name TEXT
);
CREATE TABLE link_pixels ( link_id UUID, pixel_id UUID, PRIMARY KEY (link_id, pixel_id) );
```

**API.** CRUD for pixels; attach/detach on link. Redirect service checks a
`has_pixels` flag (bitfield on the Redis cache row) and flips from 302 to a
tiny HTML template.

**UI.** Workspace settings -> "Tracking pixels" page. Link create form shows a
multiselect of configured pixels.

**Effort:** **M** (≈ 3 dev-days). Note: interstitial adds ~150-300 ms latency
to retargeted links — acceptable trade-off, document clearly.

### P0-8. Chrome extension

**One-liner.** One-click shorten of the current tab, with custom alias + tag
picker. Every platform in our comparison except Kutt/YOURLS has one. Drives
daily active usage more than any other single feature.

**Data model.** None. Uses existing API key flow.

**API.** Existing `POST /v1/links` works; just confirm CORS allows
`chrome-extension://` origins when an `Authorization: Bearer` header is used.

**UI.** New `extension/` package, MV3 manifest, React popup (reuse the admin
panel's link-create component via module extraction). Sign and publish to
Chrome Web Store + Edge Add-ons.

**Effort:** **M** (≈ 3-4 dev-days including store review).

### P0-9. Workspace switcher UI (finish what is already modeled)

**One-liner.** The task prompt states "workspace switcher UI not wired" despite
the backend supporting workspaces. Every competitor has a top-nav dropdown.
Without it our multi-tenant model is invisible to users.

**Data model.** None.

**API.** `GET /v1/workspaces/me` (list my workspaces + role), `POST
/v1/auth/switch-workspace` (set `active_workspace_id` on the session / issue a
new access token with the right `ws_id` claim).

**UI.** Top-nav dropdown: avatar, name, plan badge, "Create workspace",
"Manage members", "Settings". Persist last active workspace in localStorage
and in the JWT claim.

**Effort:** **S** (≈ 1-2 dev-days).

### P0-10. Safety scan on URL create (Google Web Risk or URLhaus)

**One-liner.** Refuse or soft-flag obviously malicious destinations at create
time. Keeps our domain off abuse lists and enables the safety interstitial
from P0-5 for flagged links. Bitly's Web Risk partnership is the industry
baseline.

**Data model.**
```sql
ALTER TABLE links
  ADD COLUMN safety_status TEXT DEFAULT 'unchecked', -- ok/warn/block
  ADD COLUMN safety_reason TEXT,
  ADD COLUMN safety_checked_at TIMESTAMPTZ;
```

**API.** Background worker calls Google Web Risk Lookup API (or local URLhaus
mirror for cost). Free tier of Web Risk covers 10k/day. On create, run
synchronously with 500 ms budget; on timeout, queue async and mark `unchecked`.

**UI.** Yellow banner on risky links; block outright for `block` status unless
the user is on Enterprise plan with override permission.

**Effort:** **M** (≈ 2-3 dev-days).

---

## 4. P1 (next quarter, shorter treatment)

| # | Feature | Why | Effort |
|---|---|---|---|
| P1-1 | **Link-in-bio pages** | Creator growth segment; Dub/Cuttly/t.ly/Bitly all ship. Needs new `bio_pages` table, public render route, block types (link, header, image, video). | L (8-10 d) |
| P1-2 | **Real-time click stream (SSE)** | Live "watch a link" view, demo-able feature. Tap ClickHouse MV + Redis pubsub. | M |
| P1-3 | **Conversion tracking (Stripe/Shopify)** | Dub's killer feature. Needs server-side event ingestion + click-id cookie + attribution window logic. | L |
| P1-4 | **SAML SSO** | Enterprise gating. Use `python-saml` or dex/Ory Hydra behind FastAPI. | M |
| P1-5 | **Audit log** | Required for SOC-2; cheap if done early. Append-only table, read-only UI. | S-M |
| P1-6 | **Colored tags + tag-filtered analytics** | Small UX polish, big perceived-value. | S |
| P1-7 | **Scheduled reports + alerts on spikes** | Email a weekly PDF. Cron + Mailgun + Chromium print. | M |
| P1-8 | **Public shareable analytics link** | Unique URL with view-only token, optionally password-gated. | S |
| P1-9 | **iOS/Android share sheet app** | Thin RN wrapper around the API. Appstore review often gates this 2 weeks. | L |
| P1-10 | **Typed SDKs (TS + Py + Go)** | Generate from OpenAPI via `openapi-generator`. Publish to npm/PyPI/proxy.golang.org. | S-M |

## 5. P2 (later, parking lot)

- SCIM 2.0 provisioning
- HubSpot / Salesforce / Mailchimp native connectors
- Approval workflow for link creation (enterprise)
- Mention + comment system on links
- Cohort / funnel analytics
- AI-powered "ask your links" chat (Bitly Assist clone)
- MCP server
- WordPress plugin
- Email-signature generator
- IP allow-listing at the auth layer
- Dedicated mobile app with offline cache

---

## 6. Architecture Considerations

### 6.1 Redirect hot path is about to get more expensive

Today's path:

```
GET /:slug
  -> Redis GET link:{slug}            (P50: 0.4 ms)
  -> (miss) Postgres SELECT ...       (P50: 3 ms)
  -> check password / expiry / max_clicks
  -> INSERT into Kafka/NATS -> Clickhouse async
  -> 302 Location
```

Adding P0-1 (smart routing), P0-5 (preview page), P0-7 (pixel interstitial),
and P0-10 (safety flag) all pile conditional work into this path. Mitigations:

1. **Pre-compile the decision tree** at link create/update time and serialize
   it onto the cached row. Redirect-service never parses JSON on the hot path —
   it decodes a small flat struct (`msgpack` or `flatbuffers`).
2. **Early-exit on the common case.** 90%+ of links have no rules, no pixel,
   no preview. Use a single `flags` byte on the cache row; if `flags == 0`,
   skip all extension checks.
3. **Interstitials are a separate route** (`/preview/:slug`, `/r/:slug` for
   pixel routes) served by a different handler — keep `/:slug` pure for
   plain redirects.
4. **Keep GeoIP in-process** via MaxMind DB mmap; the DB is ~70 MB so don't
   fetch on every request.

### 6.2 A/B requires sticky user assignment

A naive weighted random split will put the same cookie-less user in different
buckets on repeat visits, mangling downstream funnels. Options:

- **Stateless hash:** `variant = hash(ip || ua) % 100 < weight`. No storage,
  but IP changes break stickiness.
- **First-party cookie:** set `abv_{slug}=A` on first visit, 30-day TTL. Works
  for humans. Bots already ignore cookies so they fail stateless hash too —
  fine.

Recommend: cookie-first, hash fallback. Document the semantics.

### 6.3 Pixel interstitial and safety interstitial both need an HTML template

Serve a minimal (< 2 KB) HTML with:

- Preload meta refresh (safety net)
- Inline `<script>` that fires each configured pixel
- `setTimeout(() => location.replace(dest), 100)`

This is a separate Go handler (or a FastAPI endpoint if we want to share
templating). Cache-Control: private, no-store. Don't leak `dest` in the HTML
if the link is password-gated.

### 6.4 Folder hierarchy: limit depth

Allow at most 4 levels deep. Unbounded recursion makes UI drag-drop and
analytics queries painful. Enforce in `INSERT` trigger and API.

### 6.5 Bulk import: rate-limit and dedupe

CSV imports can be 100k+ rows. Stream-parse; for each row: validate, check
existing slug (if provided), apply tenant rate limit as if it were an API
call but batched. Produce a result CSV with `status,slug,reason` columns
so users can fix and re-import.

### 6.6 Conversion tracking (P1-3) needs a click-id cookie scheme

Dub's model: on redirect, set `dub_id=<uuid>` cookie on the destination
domain (only works if the destination domain opts in with a snippet) OR
append `?dub_id=<uuid>` to the destination. Our redirect is cross-origin so
we cannot set a cookie on the destination; the query-param approach is the
portable one. Destination's backend reports `conversion({dub_id, value,
currency})` to our ingest endpoint. Attribution window (default 24 h) is a
ClickHouse join. This is genuinely complex; budget 1.5-2 sprints.

### 6.7 Safety scan: make it async by default

Web Risk Lookup API has 100 ms median latency but rare 2-3 s outliers.
Blocking link creation is a bad trade. Better: return `201 Created` with
`safety_status=unchecked`, run async scan, push WebSocket event on finish,
and let the redirect path refuse unchecked links for anonymous users only.

### 6.8 Chrome extension CSP considerations

MV3 requires all extension JS to be bundled; no remote `<script src=>`. Build
with Vite's extension preset. Use a dedicated API-key flow (`extension_v1`
prefix) so users can revoke without logging out of the web app.

### 6.9 Link-in-bio (P1-1) needs its own render path

Bio pages are a public HTML route distinct from `/:slug`. They pull many
links + blocks + a theme JSON and render SSR for OG previews. Consider a
separate Next.js (or Astro) app at `bio.ourdomain.tld/@handle` so we don't
bloat the redirect-service or SPA. Analytics events should share the same
ClickHouse sink with an `event_type='bio_view'` tag.

### 6.10 Enterprise features need a "plan gating" layer early

Before we build P0-10 safety or P1-4 SSO, carve out a single
`require_plan(["business","enterprise"])` decorator in FastAPI and a matching
feature-flag table. Retrofitting gating across 50 endpoints later is a
weekend of yak-shaving we can avoid.

---

## 7. Effort Summary

| Bucket | Features | Rough dev-days |
|---|---|---|
| **P0 (now)** | 10 items above | 28-35 dev-days (1 engineer ~7-8 weeks) |
| **P1 (next Q)** | 10 items | 40-55 dev-days |
| **P2 (parking)** | 11 items | 60+ dev-days |

Suggested sequencing for P0:

1. Week 1: P0-9 workspace switcher, P0-6 UTM builder/templates (quick wins, unblock future plan-gating).
2. Week 2-3: P0-3 folders + P0-4 bulk ops (shared list-page refactor).
3. Week 4: P0-2 branded QR + P0-5 OG previews + preview page (client-side heavy).
4. Week 5-6: P0-1 smart routing (biggest architectural item, do after list refactor settles).
5. Week 7: P0-10 safety + P0-7 retargeting pixel (both touch redirect path; batch).
6. Week 8: P0-8 Chrome extension + store submission.

---

## 8. Sources

- [Bitly Introduces AI-Powered Features](https://www.prnewswire.com/news-releases/bitly-introduces-ai-powered-features-to-simplify-and-accelerate-marketing-analytics-302732666.html)
- [Bitly 2026 Expanded Link and QR Code](https://bitly.com/pages/resources/press/bitly-connection-layer-links-qr-codes-2026/)
- [Bitly Enterprise Pricing 2026](https://linklyhq.com/blog/bitly-enterprise-pricing-2020)
- [Bitly SAML SSO Support](https://support.bitly.com/hc/en-us/articles/360001482672-What-is-SAML-single-sign-on-SSO)
- [Bitly Trust & Safety](https://bitly.com/blog/trust-safety-at-bitly/)
- [Bitly Trust & Safety Deep Dive (Web Risk)](https://cloud.google.com/blog/topics/partners/bitly-ensuring-real-time-link-safety-with-web-risk-to-protect-people)
- [Bitly QR Code Generator](https://bitly.com/pages/products/qr-codes)
- [Dub.co Homepage](https://dub.co/)
- [Dub.co TechCrunch coverage](https://techcrunch.com/2025/01/16/dub-co-is-an-open-source-url-shortener-and-link-attribution-engine-packed-into-one/)
- [Dub Introducing Link Folders](https://dub.co/blog/introducing-folders)
- [Dub Collaboration Feature](https://dub.co/features/collaboration)
- [Dub Workspace Docs](https://dub.co/help/article/what-is-a-workspace)
- [Short.io Features](https://short.io/features/)
- [Short.io G2 reviews 2026](https://www.g2.com/products/short-io/reviews)
- [Cuttly Analytics Guide 2025-2026](https://cutt.ly/resources/blog/url-shortener-analytics-guide)
- [Cuttly Best Bitly Alternative 2026](https://cutt.ly/resources/blog/best-bitly-alternative-2026)
- [Cuttly QR with Logo 2026](https://cutt.ly/resources/blog/how-to-create-qr-code-with-logo-2026)
- [Rebrandly Homepage](https://www.rebrandly.com/)
- [Rebrandly Enterprise](https://www.rebrandly.com/enterprise)
- [Rebrandly vs Bitly 2026](https://www.rebrandly.com/blog/rebrandly-vs-bitly)
- [T.LY Homepage](https://t.ly/)
- [T.LY Blog](https://t.ly/blog/worlds-shortest-url-shortener-t-ly)
- [Kutt.it Homepage](https://kutt.it/)
- [Kutt GitHub](https://github.com/thedevs-network/kutt)
- [YOURLS Docs](https://yourls.org/docs)
- [YOURLS Awesome Plugins](https://github.com/YOURLS/awesome)
- [TinyURL 2026 Pricing](https://www.getapp.com/marketing-software/a/tinyurl-1/)
- [Bitly vs TinyURL 2026 by Dub](https://dub.co/blog/bitly-vs-tinyurl)
- [LinkSplit Retargeting Pixels](https://linksplit.io/pixel-url-shortener)
- [Rocketlink Retargeting](https://rocketlink.io/)
- [Replug Link Marketing Platform](https://replug.io)
