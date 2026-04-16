-- ============================================================
-- URL Shortener — ClickHouse analytics schema
-- Source: HLA section 3.2
-- Runs once on first container start via /docker-entrypoint-initdb.d.
-- Idempotent: CREATE ... IF NOT EXISTS.
-- ============================================================

CREATE DATABASE IF NOT EXISTS analytics;

-- ---- Raw click events --------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.clicks (
    click_id        UUID DEFAULT generateUUIDv4(),
    short_code      String,

    clicked_at      DateTime64(3, 'UTC'),

    -- user (enriched)
    ip_hash         String,
    country_code    LowCardinality(String),
    country_name    LowCardinality(String),
    city            String,
    region          String,
    latitude        Float64,
    longitude       Float64,

    -- device (UA-parser)
    device_type     LowCardinality(String),
    browser         LowCardinality(String),
    browser_version String,
    os              LowCardinality(String),
    os_version      String,

    -- referer
    referer_url     String,
    referer_domain  LowCardinality(String),
    referer_type    LowCardinality(String),

    -- bot detection
    is_bot          UInt8 DEFAULT 0,
    bot_name        LowCardinality(String),

    -- UTM (destination URL)
    utm_source      LowCardinality(String),
    utm_medium      LowCardinality(String),
    utm_campaign    LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(clicked_at)
ORDER BY (short_code, clicked_at)
TTL toDateTime(clicked_at) + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;

-- ---- Daily rollup ------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.clicks_daily_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (short_code, day, country_code, device_type, referer_type)
AS
SELECT
    short_code,
    toDate(clicked_at) AS day,
    country_code,
    device_type,
    referer_type,
    count()               AS click_count,
    uniqExact(ip_hash)    AS unique_visitors
FROM analytics.clicks
WHERE is_bot = 0
GROUP BY short_code, day, country_code, device_type, referer_type;

-- ---- Hourly rollup -----------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.clicks_hourly_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (short_code, hour)
AS
SELECT
    short_code,
    toStartOfHour(clicked_at) AS hour,
    count()                   AS click_count,
    uniqExact(ip_hash)        AS unique_visitors
FROM analytics.clicks
WHERE is_bot = 0
GROUP BY short_code, hour;
