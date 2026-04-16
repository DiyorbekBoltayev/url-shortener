-- ============================================================
-- URL Shortener — PostgreSQL init schema
-- Source of truth: HLA section 3.1
-- Runs once on first container start via /docker-entrypoint-initdb.d.
-- Idempotent: safe to re-run.
-- ============================================================

-- ---- Extensions -------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---- Generic trigger: updated_at = NOW() on UPDATE -------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    plan            VARCHAR(20) DEFAULT 'free',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- workspaces
-- ============================================================
CREATE TABLE IF NOT EXISTS workspaces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,
    owner_id        UUID NOT NULL REFERENCES users(id),
    plan            VARCHAR(20) DEFAULT 'free',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_id ON workspaces(owner_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug);

DROP TRIGGER IF EXISTS trg_workspaces_updated_at ON workspaces;
CREATE TRIGGER trg_workspaces_updated_at
    BEFORE UPDATE ON workspaces
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- workspace_members (junction)
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(20) DEFAULT 'member',
    joined_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members(user_id);

-- ============================================================
-- domains
-- ============================================================
CREATE TABLE IF NOT EXISTS domains (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    domain          VARCHAR(255) UNIQUE NOT NULL,
    is_verified     BOOLEAN DEFAULT FALSE,
    verified_at     TIMESTAMPTZ,
    ssl_status      VARCHAR(20) DEFAULT 'pending',
    dns_token       VARCHAR(64),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_domains_domain ON domains(domain);
CREATE INDEX IF NOT EXISTS idx_domains_workspace_id ON domains(workspace_id);

DROP TRIGGER IF EXISTS trg_domains_updated_at ON domains;
CREATE TRIGGER trg_domains_updated_at
    BEFORE UPDATE ON domains
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- urls (asosiy jadval)
-- ============================================================
CREATE TABLE IF NOT EXISTS urls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    short_code      VARCHAR(10) UNIQUE NOT NULL,
    long_url        TEXT NOT NULL,
    title           VARCHAR(500),

    -- egalik
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    domain_id       UUID REFERENCES domains(id) ON DELETE SET NULL,

    -- sozlamalar
    is_active       BOOLEAN DEFAULT TRUE,
    password_hash   VARCHAR(255),
    expires_at      TIMESTAMPTZ,
    max_clicks      INTEGER,

    -- metadata
    tags            TEXT[] DEFAULT '{}',
    utm_source      VARCHAR(255),
    utm_medium      VARCHAR(255),
    utm_campaign    VARCHAR(255),

    -- denormalizatsiya
    click_count     BIGINT DEFAULT 0,
    last_clicked_at TIMESTAMPTZ,

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_urls_short_code ON urls(short_code);
CREATE INDEX IF NOT EXISTS idx_urls_user_id ON urls(user_id);
CREATE INDEX IF NOT EXISTS idx_urls_workspace_id ON urls(workspace_id);
CREATE INDEX IF NOT EXISTS idx_urls_domain_id ON urls(domain_id);
CREATE INDEX IF NOT EXISTS idx_urls_created_at ON urls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_urls_expires_at ON urls(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_urls_tags ON urls USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_urls_long_url_hash ON urls(md5(long_url));
-- Trigram GIN index for ILIKE '%foo%' searches on long_url / short_code.
CREATE INDEX IF NOT EXISTS idx_urls_long_url_trgm   ON urls USING GIN (long_url gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_urls_short_code_trgm ON urls USING GIN (short_code gin_trgm_ops);

DROP TRIGGER IF EXISTS trg_urls_updated_at ON urls;
CREATE TRIGGER trg_urls_updated_at
    BEFORE UPDATE ON urls
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- api_keys
-- ============================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    key_hash        VARCHAR(255) UNIQUE NOT NULL,
    key_prefix      VARCHAR(10) NOT NULL,
    scopes          TEXT[] DEFAULT '{read,write}',
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_workspace_id ON api_keys(workspace_id);

DROP TRIGGER IF EXISTS trg_api_keys_updated_at ON api_keys;
CREATE TRIGGER trg_api_keys_updated_at
    BEFORE UPDATE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- webhooks
-- ============================================================
CREATE TABLE IF NOT EXISTS webhooks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    secret          VARCHAR(255) NOT NULL,
    events          TEXT[] NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    last_triggered  TIMESTAMPTZ,
    failure_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_workspace_id ON webhooks(workspace_id);

DROP TRIGGER IF EXISTS trg_webhooks_updated_at ON webhooks;
CREATE TRIGGER trg_webhooks_updated_at
    BEFORE UPDATE ON webhooks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- short_code_pool (KGS)
-- ============================================================
CREATE TABLE IF NOT EXISTS short_code_pool (
    code            VARCHAR(10) PRIMARY KEY,
    is_used         BOOLEAN DEFAULT FALSE,
    claimed_by      VARCHAR(50),
    claimed_at      TIMESTAMPTZ,
    used_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pool_available ON short_code_pool(is_used) WHERE is_used = FALSE;

-- ============================================================
-- P0 FEATURES — added 2026-04-14 (research/06-competitive-features.md)
-- ============================================================

-- ---- folders (1:N organization) ----------------------------------
CREATE TABLE IF NOT EXISTS folders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    parent_id       UUID REFERENCES folders(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    color           VARCHAR(16),
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_folders_workspace ON folders(workspace_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);

DROP TRIGGER IF EXISTS trg_folders_updated_at ON folders;
CREATE TRIGGER trg_folders_updated_at
    BEFORE UPDATE ON folders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---- utm_templates -----------------------------------------------
CREATE TABLE IF NOT EXISTS utm_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    utm_source      VARCHAR(255),
    utm_medium      VARCHAR(255),
    utm_campaign    VARCHAR(255),
    utm_term        VARCHAR(255),
    utm_content     VARCHAR(255),
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_utm_templates_workspace ON utm_templates(workspace_id);

-- ---- retarget_pixels + link_pixels -------------------------------
CREATE TABLE IF NOT EXISTS retarget_pixels (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    kind            VARCHAR(20) NOT NULL,        -- fb|ga4|gtm|linkedin|tiktok|pinterest|twitter
    pixel_id        VARCHAR(255) NOT NULL,
    name            VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_retarget_pixels_workspace ON retarget_pixels(workspace_id);

CREATE TABLE IF NOT EXISTS link_pixels (
    url_id          UUID REFERENCES urls(id) ON DELETE CASCADE,
    pixel_id        UUID REFERENCES retarget_pixels(id) ON DELETE CASCADE,
    PRIMARY KEY (url_id, pixel_id)
);

-- ---- bulk_jobs (async CSV import/export + bulk_patch) -----------
CREATE TABLE IF NOT EXISTS bulk_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id),
    kind            VARCHAR(32) NOT NULL,        -- import|export|bulk_patch
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    total           INT DEFAULT 0,
    done            INT DEFAULT 0,
    failed          INT DEFAULT 0,
    params          JSONB,
    result_url      TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bulk_jobs_workspace_status ON bulk_jobs(workspace_id, status, created_at DESC);

-- ---- urls new columns (P0 features) ------------------------------
ALTER TABLE urls
    ADD COLUMN IF NOT EXISTS folder_id         UUID REFERENCES folders(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS routing_rules     JSONB,
    ADD COLUMN IF NOT EXISTS qr_style          JSONB,
    ADD COLUMN IF NOT EXISTS preview_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS og_title          TEXT,
    ADD COLUMN IF NOT EXISTS og_description    TEXT,
    ADD COLUMN IF NOT EXISTS og_image_url      TEXT,
    ADD COLUMN IF NOT EXISTS favicon_url       TEXT,
    ADD COLUMN IF NOT EXISTS og_fetched_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS safety_status     VARCHAR(16) NOT NULL DEFAULT 'unchecked',
    ADD COLUMN IF NOT EXISTS safety_reason     TEXT,
    ADD COLUMN IF NOT EXISTS safety_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_urls_folder ON urls(workspace_id, folder_id);
CREATE INDEX IF NOT EXISTS idx_urls_safety ON urls(safety_status) WHERE safety_status <> 'ok';
