# P0 Features Implementation Plan

## Parallel streams (after unified DB migration)

| Stream | Scope | Repos touched |
|---|---|---|
| **S0 (blocking)** | Alembic 003 + init.sql updates — ALL new schema | infrastructure, api-service |
| **S1 Backend CRUD** | Folders, UTM templates, Retarget pixels, Workspace API, Bulk jobs, Safety + Preview stubs | api-service |
| **S2 Redirect engine** | Routing rules (A/B + device + geo), pixel interstitial page | redirect-service |
| **S3 Branded QR** | QR style options backend + UI panel | api-service + admin-panel |
| **S4 Background workers** | OG preview fetcher, Safety scan, CSV import worker | api-service lifespan tasks |
| **S5 Admin UI** | All P0 frontend: folders tree, UTM builder, workspace switcher, bulk CSV wizard, preview toggle, routing tab, pixel picker, safety banner | admin-panel |
| **S6 Chrome extension** | MV3 popup, API key flow | NEW repo `chrome-extension/` |

## Unified DB delta (S0)

### `urls` table — new columns
```sql
ALTER TABLE urls
  ADD COLUMN IF NOT EXISTS folder_id UUID,
  ADD COLUMN IF NOT EXISTS routing_rules JSONB,
  ADD COLUMN IF NOT EXISTS qr_style JSONB,
  ADD COLUMN IF NOT EXISTS preview_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS og_title TEXT,
  ADD COLUMN IF NOT EXISTS og_description TEXT,
  ADD COLUMN IF NOT EXISTS og_image_url TEXT,
  ADD COLUMN IF NOT EXISTS favicon_url TEXT,
  ADD COLUMN IF NOT EXISTS og_fetched_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS safety_status TEXT NOT NULL DEFAULT 'unchecked',
  ADD COLUMN IF NOT EXISTS safety_reason TEXT,
  ADD COLUMN IF NOT EXISTS safety_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_urls_folder ON urls(workspace_id, folder_id);
CREATE INDEX IF NOT EXISTS idx_urls_safety ON urls(safety_status) WHERE safety_status <> 'ok';
```

### New tables
```sql
CREATE TABLE IF NOT EXISTS folders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  parent_id UUID REFERENCES folders(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  color VARCHAR(16),
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_folders_workspace ON folders(workspace_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);

CREATE TABLE IF NOT EXISTS utm_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  utm_source VARCHAR(255),
  utm_medium VARCHAR(255),
  utm_campaign VARCHAR(255),
  utm_term VARCHAR(255),
  utm_content VARCHAR(255),
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_utm_templates_workspace ON utm_templates(workspace_id);

CREATE TABLE IF NOT EXISTS retarget_pixels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  kind VARCHAR(20) NOT NULL, -- fb, ga4, gtm, linkedin, tiktok, pinterest, twitter
  pixel_id VARCHAR(255) NOT NULL,
  name VARCHAR(255),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_retarget_pixels_workspace ON retarget_pixels(workspace_id);

CREATE TABLE IF NOT EXISTS link_pixels (
  url_id UUID REFERENCES urls(id) ON DELETE CASCADE,
  pixel_id UUID REFERENCES retarget_pixels(id) ON DELETE CASCADE,
  PRIMARY KEY (url_id, pixel_id)
);

CREATE TABLE IF NOT EXISTS bulk_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  kind VARCHAR(32) NOT NULL, -- import, export, bulk_patch
  status VARCHAR(16) NOT NULL DEFAULT 'pending', -- pending, running, done, failed
  total INT DEFAULT 0,
  done INT DEFAULT 0,
  failed INT DEFAULT 0,
  params JSONB,
  result_url TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bulk_jobs_workspace_status ON bulk_jobs(workspace_id, status, created_at DESC);

ALTER TABLE urls ADD CONSTRAINT fk_urls_folder FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL;
```

### Redis cache row enrichment
Redirect service caches now store:
- `url:{code}` → still the destination long_url
- `url:meta:{code}` → HASH with `{expires_at, password_hash, is_active, max_clicks, has_rules:0/1, has_pixels:0/1, safety_status}`
- `url:rules:{code}` → JSON string with routing rules (only if has_rules=1; TTL 24h)
- `url:pixels:{code}` → JSON array of pixel config (only if has_pixels=1)

API-service is responsible for writing these on link create/update.

---

## Data contracts

### routing_rules JSON
```json
{
  "ab": [{"url":"https://a.example","weight":50},{"url":"https://b.example","weight":50}],
  "device": {"ios":"https://ios...","android":"https://android...","desktop":"https://..."},
  "geo": {"US":"...","DE":"...","default":"..."}
}
```
Evaluation order: geo → device → ab → fallback to `urls.long_url`.

### qr_style JSON
```json
{ "fg":"#111","bg":"#fff","logo_url":"https://...","frame":"rounded","dots":"rounded","corners":"extra-rounded" }
```

### pixel kind allowed values
`fb | ga4 | gtm | linkedin | tiktok | pinterest | twitter`

### bulk_jobs.params
- import: `{ csv_url, column_map:{long_url,title,tag,...}, default_tag }`
- export: `{ filter:{workspace_id, folder_id, tags, q}, format:"csv" }`
- bulk_patch: `{ ids:[...], patch:{tag?,folder_id?,is_active?,expires_at?} }`

---

## Phased execution

1. **S0** — I write DB migration + init.sql + contract (10 min)
2. **S1-S6** — 6 parallel agents (30-60 min)
3. Rebuild all images
4. Smoke test + review
