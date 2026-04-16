# URL Shortener — High-Level Architecture (HLA)

## Strategiya: FastAPI + Go Gibrid Arxitektura

> **Redirect xizmati** — Go (Fiber) | **Admin API** — FastAPI (Python) | **Ma'lumotlar** — PostgreSQL + Redis + ClickHouse

---

## Mundarija

1. [Umumiy Tizim Arxitekturasi](#1-umumiy-tizim-arxitekturasi)
2. [Xizmatlar Taqsimoti](#2-xizmatlar-taqsimoti)
3. [Ma'lumotlar Bazasi Arxitekturasi](#3-malumotlar-bazasi-arxitekturasi)
4. [Keshlash Strategiyasi (Redis)](#4-keshlash-strategiyasi-redis)
5. [Message Queue va Event Processing](#5-message-queue-va-event-processing)
6. [Analitika Pipeline](#6-analitika-pipeline)
7. [API Dizayni](#7-api-dizayni)
8. [Xavfsizlik Arxitekturasi](#8-xavfsizlik-arxitekturasi)
9. [Infratuzilma va DevOps](#9-infratuzilma-va-devops)
10. [Monitoring va Observability](#10-monitoring-va-observability)
11. [Joylashtirish Arxitekturasi](#11-joylashtirish-arxitekturasi)
12. [Texnologiyalar To'liq Ro'yxati](#12-texnologiyalar-toliq-royxati)
13. [Papka Tuzilmasi](#13-papka-tuzilmasi)
14. [Ma'lumot Oqimi Diagrammalari](#14-malumot-oqimi-diagrammalari)
15. [Masshtablash Rejasi](#15-masshtablash-rejasi)

---

## 1. Umumiy Tizim Arxitekturasi

```
                            ┌──────────────────────────────────┐
                            │         FOYDALANUVCHILAR          │
                            │   (Brauzer, Mobil, API Klient)    │
                            └──────────────┬───────────────────┘
                                           │
                                           ▼
                            ┌──────────────────────────────────┐
                            │        NGINX / TRAEFIK           │
                            │      (Reverse Proxy + LB)         │
                            │                                    │
                            │  /{code}  → Go Redirect Xizmati   │
                            │  /api/*   → FastAPI Admin API      │
                            │  /dash/*  → Frontend (React)       │
                            └─────┬────────────────┬────────────┘
                                  │                │
                    ┌─────────────▼──┐    ┌───────▼──────────────┐
                    │                │    │                        │
                    │  GO REDIRECT   │    │   FASTAPI ADMIN API    │
                    │   XIZMATI      │    │                        │
                    │                │    │  • URL CRUD             │
                    │  • GET /{code} │    │  • Foydalanuvchi Auth   │
                    │  • Redis o'qish│    │  • Analitika API        │
                    │  • 302 Redirect│    │  • Domen boshqarish     │
                    │  • Click event │    │  • QR Kod yaratish      │
                    │    chiqarish   │    │  • Webhook boshqarish   │
                    │                │    │  • Rate limiting         │
                    └───┬────────┬───┘    └───┬──────────┬─────────┘
                        │        │            │          │
               ┌────────▼──┐  ┌─▼────────┐  ┌▼────────┐ │
               │   REDIS    │  │  REDIS   │  │PostgreSQL│ │
               │   (Kesh)   │  │ STREAMS  │  │  (Asosiy │ │
               │            │  │ (Queue)  │  │   Baza)  │ │
               │ URL xarita │  │          │  │          │ │
               │ Rate limit │  │  Click   │  │  URLs    │ │
               │ Session    │  │  events  │  │  Users   │ │
               └────────────┘  └────┬─────┘  │  Domains │ │
                                    │        │  API Keys│ │
                                    ▼        └──────────┘ │
                            ┌──────────────┐              │
                            │   ANALYTICS   │              │
                            │    WORKER     │◄─────────────┘
                            │   (Python)    │
                            │              │
                            │ • GeoIP lookup│
                            │ • UA parsing  │
                            │ • Aggregation │
                            └──────┬───────┘
                                   │
                                   ▼
                            ┌──────────────┐
                            │  CLICKHOUSE   │
                            │  (Analitika   │
                            │    Bazasi)    │
                            │              │
                            │ • Raw clicks  │
                            │ • Aggregated  │
                            │   stats       │
                            └──────────────┘
```

---

## 2. Xizmatlar Taqsimoti

### 2.1 Go Redirect Xizmati

**Maqsad:** Faqat bitta vazifa — qisqa kodni uzun URLga yo'naltirish. Eng tez, eng yengil.

| Xususiyat | Tafsilot |
|---|---|
| **Til** | Go 1.22+ |
| **Framework** | Fiber v2 (Express-inspired, fasthttp ustiga qurilgan) |
| **Redis klient** | go-redis/redis v9 |
| **Port** | :8080 |
| **Endpointlar** | `GET /{code}` → 302 Redirect, `GET /health` → Health check |
| **Kechikish maqsadi** | < 5ms (Redis kesh hit), < 20ms (DB fallback) |
| **Throughput** | Bitta instansiya 50,000-100,000 req/s |

**Ish oqimi:**
```
1. So'rov keldi: GET /aB3xK9
2. Redis dan qidirish: GET url:aB3xK9
3. Agar topilsa (CACHE HIT ~90%):
   → GeoIP lookup (xotirada, ~1-5 mikrosekund — kechikish qo'shmaydi)
   → Redis Streams ga click event chiqarish (asinxron, XADD)
     Event: { code, ts, ip, ua, ref, country, city }
   → HTTP 302 Location: <uzun_url> qaytarish
4. Agar topilmasa (CACHE MISS):
   → PostgreSQL dan qidirish
   → Agar topilsa → Redis ga yozish (SET url:aB3xK9 <uzun_url> EX 86400)
   → Redirect qaytarish
5. Agar hech qayerda topilmasa:
   → HTTP 404 qaytarish
```

> **Optimallashtirish:** GeoIP lookup Go redirect xizmatida xotirada bajariladi (MaxMind `.mmdb` faylni bir marta yuklaydi, keyin har bir qidirish ~1-5 mikrosekund). Bu Worker dagi yukni kamaytiradi va analitika ma'lumotlari to'liqroq bo'ladi.

**Nega Go + Fiber:**
- fasthttp kutubxonasi ustiga qurilgan — Go standart net/http dan 10x tez
- Goroutinelar — millionlab bir vaqtdagi ulanishlarni boshqarish
- Minimal xotira ishi — bitta instansiya ~20-50MB RAM
- Kompilyatsiya qilingan binary — Docker rasm hajmi ~15MB (scratch)
- GC pauzalari minimal — sub-millisekund

### 2.2 FastAPI Admin API

**Maqsad:** Barcha biznes logikasi — URL yaratish, foydalanuvchi boshqaruvi, analitika, integratsiyalar.

| Xususiyat | Tafsilot |
|---|---|
| **Til** | Python 3.12+ |
| **Framework** | FastAPI 0.110+ |
| **ASGI Server** | Uvicorn (uvloop bilan) |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Validatsiya** | Pydantic v2 |
| **Port** | :8000 |
| **Kechikish maqsadi** | < 100ms (CRUD operatsiyalar) |

**Mas'uliyat sohalari:**
```
URL Boshqarish:
  ├── POST   /api/v1/urls          → URL yaratish (qisqartirish)
  ├── GET    /api/v1/urls          → Foydalanuvchi URLlarini ro'yxatlash
  ├── GET    /api/v1/urls/{id}     → URL tafsilotlari
  ├── PATCH  /api/v1/urls/{id}     → URL yangilash
  ├── DELETE /api/v1/urls/{id}     → URL o'chirish
  └── POST   /api/v1/urls/bulk     → Ommaviy URL yaratish

Analitika:
  ├── GET /api/v1/analytics/{code}/summary     → Umumiy statistika
  ├── GET /api/v1/analytics/{code}/timeseries  → Vaqt bo'yicha bosishlar
  ├── GET /api/v1/analytics/{code}/geo         → Geografik taqsimot
  ├── GET /api/v1/analytics/{code}/devices     → Qurilma taqsimoti
  ├── GET /api/v1/analytics/{code}/referrers   → Referrer taqsimoti
  └── GET /api/v1/analytics/dashboard          → Umumiy dashboard

Foydalanuvchi Boshqaruvi:
  ├── POST /api/v1/auth/register   → Ro'yxatdan o'tish
  ├── POST /api/v1/auth/login      → Kirish (JWT)
  ├── POST /api/v1/auth/refresh    → Token yangilash
  ├── GET  /api/v1/users/me        → Profil
  └── GET  /api/v1/users/me/urls   → Mening URLlarim

Domen Boshqarish:
  ├── POST   /api/v1/domains       → Maxsus domen qo'shish
  ├── GET    /api/v1/domains       → Domenlar ro'yxati
  ├── DELETE /api/v1/domains/{id}  → Domen o'chirish
  └── POST   /api/v1/domains/{id}/verify → DNS tekshirish

API Kalitlar:
  ├── POST   /api/v1/api-keys      → Yangi kalit yaratish
  ├── GET    /api/v1/api-keys      → Kalitlar ro'yxati
  └── DELETE /api/v1/api-keys/{id} → Kalit o'chirish

QR Kodlar:
  └── GET /api/v1/urls/{id}/qr     → QR kod yaratish (PNG/SVG)

Webhooklar:
  ├── POST   /api/v1/webhooks      → Webhook qo'shish
  ├── GET    /api/v1/webhooks      → Webhooklar ro'yxati
  └── DELETE /api/v1/webhooks/{id} → Webhook o'chirish
```

### 2.3 Analytics Worker

**Maqsad:** Redis Streams dan click eventlarni o'qib, boyitib (GeoIP, UA parsing), ClickHouse ga yozish.

| Xususiyat | Tafsilot |
|---|---|
| **Til** | Python 3.12+ |
| **Framework** | Oddiy Python (asyncio) |
| **GeoIP** | MaxMind GeoLite2 (geoip2 kutubxonasi) |
| **UA Parsing** | ua-parser yoki user-agents kutubxonasi |
| **ClickHouse klient** | clickhouse-connect |

**Ish oqimi:**
```
1. Redis Streams dan click eventlarni o'qish (XREADGROUP)
   Event: { short_code, timestamp, ip, user_agent, referer }

2. Boyitish (Enrichment):
   ├── GeoIP → mamlakat, shahar, mintaqa
   ├── UA Parsing → qurilma_turi, brauzer, OS
   ├── Bot aniqlash → is_bot (ma'lum UA filtrlash)
   └── Referer parsing → referer_domain, referer_type

3. Batch yozish — ClickHouse ga (har 1 sekund yoki 1000 event)
   INSERT INTO clicks (short_code, clicked_at, country, city, ...)

4. Real-time counter yangilash — Redis da
   HINCRBY stats:{code} total 1
   HINCRBY stats:{code} {country} 1

5. ACK — Redis Streams da qayta ishlanganini tasdiqlash (XACK)
```

### 2.4 Frontend (React/Next.js)

| Xususiyat | Tafsilot |
|---|---|
| **Framework** | Next.js 14+ (App Router) yoki React + Vite |
| **UI Kutubxona** | shadcn/ui + Tailwind CSS |
| **Diagrammalar** | Recharts yoki Tremor |
| **State** | Zustand yoki TanStack Query |
| **Port** | :3000 |

**Sahifalar:**
```
/                    → Landing page + URL qisqartirish formasi
/dashboard           → Analitika dashboard
/dashboard/links     → Linklar boshqaruvi
/dashboard/links/:id → Link tafsilotlari + analitika
/dashboard/domains   → Domenlar boshqaruvi
/dashboard/settings  → Sozlamalar, API kalitlar
/login               → Kirish
/register            → Ro'yxatdan o'tish
```

---

## 3. Ma'lumotlar Bazasi Arxitekturasi

### 3.1 PostgreSQL — Asosiy Ma'lumotlar Bazasi

**Versiya:** PostgreSQL 16+
**ORM:** SQLAlchemy 2.0 (async mode, asyncpg driver)
**Migration:** Alembic

**Nega PostgreSQL:**
- ACID tranzaksiyalar — URL yaratishda noyoblik kafolati
- JSONB — moslashuvchan metadata saqlash
- Yetuk indekslash — B-tree, Hash, GIN
- Kengaytmalar — pgcrypto (xeshlash), pg_trgm (qidirish)
- Go va Python uchun ajoyib driverlar (pgx, asyncpg)

#### Sxema Dizayni

```sql
-- ============================================
-- Foydalanuvchilar
-- ============================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    plan            VARCHAR(20) DEFAULT 'free',  -- free, pro, business, enterprise
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

-- ============================================
-- Tashkilotlar / Ish Fazolari
-- ============================================
CREATE TABLE workspaces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,
    owner_id        UUID NOT NULL REFERENCES users(id),
    plan            VARCHAR(20) DEFAULT 'free',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE workspace_members (
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(20) DEFAULT 'member',  -- owner, admin, member, viewer
    joined_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id)
);

-- ============================================
-- Maxsus Domenlar
-- ============================================
CREATE TABLE domains (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    domain          VARCHAR(255) UNIQUE NOT NULL,  -- masalan: go.mybrand.uz
    is_verified     BOOLEAN DEFAULT FALSE,
    verified_at     TIMESTAMPTZ,
    ssl_status      VARCHAR(20) DEFAULT 'pending', -- pending, active, failed
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_domains_domain ON domains(domain);

-- ============================================
-- URL Xaritalari (Asosiy jadval)
-- ============================================
CREATE TABLE urls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    short_code      VARCHAR(10) UNIQUE NOT NULL,
    long_url        TEXT NOT NULL,
    title           VARCHAR(500),
    
    -- Egalik
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    domain_id       UUID REFERENCES domains(id) ON DELETE SET NULL,
    
    -- Sozlamalar
    is_active       BOOLEAN DEFAULT TRUE,
    password_hash   VARCHAR(255),           -- parol bilan himoyalangan
    expires_at      TIMESTAMPTZ,            -- muddati tugash
    max_clicks      INTEGER,                -- maksimum bosishlar
    
    -- Metadata
    tags            TEXT[] DEFAULT '{}',     -- PostgreSQL array
    utm_source      VARCHAR(255),
    utm_medium      VARCHAR(255),
    utm_campaign    VARCHAR(255),
    
    -- Denormalizatsiya (tez ko'rish uchun)
    click_count     BIGINT DEFAULT 0,
    last_clicked_at TIMESTAMPTZ,
    
    -- Vaqt tamg'alari
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Asosiy indekslar
CREATE UNIQUE INDEX idx_urls_short_code ON urls(short_code);
CREATE INDEX idx_urls_user_id ON urls(user_id);
CREATE INDEX idx_urls_workspace_id ON urls(workspace_id);
CREATE INDEX idx_urls_domain_id ON urls(domain_id);
CREATE INDEX idx_urls_created_at ON urls(created_at DESC);
CREATE INDEX idx_urls_expires_at ON urls(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_urls_tags ON urls USING GIN(tags);
CREATE INDEX idx_urls_long_url_hash ON urls(md5(long_url));  -- deduplikatsiya uchun

-- ============================================
-- API Kalitlar
-- ============================================
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    key_hash        VARCHAR(255) UNIQUE NOT NULL,  -- SHA-256 xeshi
    key_prefix      VARCHAR(10) NOT NULL,          -- "usk_a3Bx..." (ko'rsatish uchun)
    scopes          TEXT[] DEFAULT '{read,write}',
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);

-- ============================================
-- Webhooklar
-- ============================================
CREATE TABLE webhooks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    secret          VARCHAR(255) NOT NULL,          -- HMAC imzo uchun
    events          TEXT[] NOT NULL,                 -- ['link.created', 'link.clicked']
    is_active       BOOLEAN DEFAULT TRUE,
    last_triggered  TIMESTAMPTZ,
    failure_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- Qisqa Kodlar Havzasi (KGS — Key Generation Service)
-- ============================================
CREATE TABLE short_code_pool (
    code            VARCHAR(10) PRIMARY KEY,
    is_used         BOOLEAN DEFAULT FALSE,
    claimed_by      VARCHAR(50),                    -- qaysi instansiya olgan
    claimed_at      TIMESTAMPTZ,
    used_at         TIMESTAMPTZ
);

CREATE INDEX idx_pool_available ON short_code_pool(is_used) WHERE is_used = FALSE;
```

#### PostgreSQL Konfiguratsiya

```ini
# postgresql.conf (asosiy sozlamalar)
max_connections = 200
shared_buffers = 2GB              # RAMning 25%
effective_cache_size = 6GB        # RAMning 75%
work_mem = 16MB
maintenance_work_mem = 512MB
random_page_cost = 1.1            # SSD uchun
effective_io_concurrency = 200    # SSD uchun

# WAL sozlamalari
wal_buffers = 64MB
checkpoint_completion_target = 0.9
max_wal_size = 2GB

# Connection pooling (PgBouncer tavsiya)
# pgbouncer.ini: pool_mode = transaction, max_client_conn = 1000
```

### 3.2 ClickHouse — Analitika Bazasi

**Versiya:** ClickHouse 24+
**Nega ClickHouse:**
- Ustun-yo'naltirilgan — analitik so'rovlar uchun 100-1000x tezroq
- Siqish — 10:1 nisbat, disk bo'shlig'ini tejaydi
- MergeTree engine — vaqt seriyali ma'lumotlar uchun optimallashtirilgan
- Milliardlab qatorlarni sekundlarda so'rash

#### ClickHouse Sxema

```sql
-- ============================================
-- Raw Click Events (asosiy analitika jadvali)
-- ============================================
CREATE TABLE clicks (
    -- Identifikatorlar
    click_id        UUID DEFAULT generateUUIDv4(),
    short_code      String,
    
    -- Vaqt
    clicked_at      DateTime64(3, 'UTC'),
    
    -- Foydalanuvchi ma'lumotlari (boyitilgan)
    ip_hash         String,             -- xeshlangan IP (maxfiylik)
    country_code    LowCardinality(String),
    country_name    LowCardinality(String),
    city            String,
    region          String,
    latitude        Float64,
    longitude       Float64,
    
    -- Qurilma ma'lumotlari (UA dan tahlil)
    device_type     LowCardinality(String),  -- desktop, mobile, tablet
    browser         LowCardinality(String),  -- Chrome, Firefox, Safari
    browser_version String,
    os              LowCardinality(String),  -- Windows, macOS, iOS, Android
    os_version      String,
    
    -- Referrer
    referer_url     String,
    referer_domain  LowCardinality(String),
    referer_type    LowCardinality(String),  -- social, search, direct, email, other
    
    -- Bot aniqlash
    is_bot          UInt8 DEFAULT 0,
    bot_name        LowCardinality(String),
    
    -- UTM parametrlari (manzil URL dan)
    utm_source      LowCardinality(String),
    utm_medium      LowCardinality(String),
    utm_campaign    LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(clicked_at)           -- Oylik partitsiya
ORDER BY (short_code, clicked_at)           -- Asosiy tartiblash kaliti
TTL clicked_at + INTERVAL 2 YEAR           -- 2 yildan keyin avtomatik o'chirish
SETTINGS index_granularity = 8192;

-- ============================================
-- Materialized View: Kunlik Statistika
-- ============================================
CREATE MATERIALIZED VIEW clicks_daily_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (short_code, day, country_code, device_type, referer_type)
AS SELECT
    short_code,
    toDate(clicked_at) AS day,
    country_code,
    device_type,
    referer_type,
    count() AS click_count,
    uniqExact(ip_hash) AS unique_visitors
FROM clicks
WHERE is_bot = 0
GROUP BY short_code, day, country_code, device_type, referer_type;

-- ============================================
-- Materialized View: Soatlik Statistika
-- ============================================
CREATE MATERIALIZED VIEW clicks_hourly_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (short_code, hour)
AS SELECT
    short_code,
    toStartOfHour(clicked_at) AS hour,
    count() AS click_count,
    uniqExact(ip_hash) AS unique_visitors
FROM clicks
WHERE is_bot = 0
GROUP BY short_code, hour;
```

#### ClickHouse Konfiguratsiya

```xml
<!-- config.xml asosiy sozlamalari -->
<max_memory_usage>8000000000</max_memory_usage>  <!-- 8GB -->
<max_threads>8</max_threads>
<max_insert_block_size>1048576</max_insert_block_size>
```

---

## 4. Keshlash Strategiyasi (Redis)

**Versiya:** Redis 7.2+ (Redis Stack tavsiya — RedisJSON, RedisSearch qo'shimcha modullari bilan)

### Redis Foydalanish Holatlari

```
Redis Instance #1: URL KESH (port 6379)
├── url:{short_code} → uzun URL          (STRING, TTL: 24 soat)
├── url:meta:{short_code} → metadata     (HASH: user_id, domain, expires_at)
└── Maqsad: Redirect xizmati uchun tez qidirish

Redis Instance #2: APPLICATION (port 6380)
├── rate:{ip}:{endpoint} → counter       (STRING + EXPIRE, rate limiting)
├── session:{token} → user data          (HASH, TTL: 7 kun)
├── stats:{short_code} → real-time stats (HASH: total, unique, {country}...)
├── api_key:{hash} → key metadata        (HASH, API kalit keshi)
└── blacklist:url:{hash} → 1             (SET, bloklangan URLlar)

Redis Streams: EVENT QUEUE (port 6380)
└── stream:clicks → click events         (STREAM, analitika uchun)
```

### Redis Kalit Sxemalari

```
# URL Kesh (Redirect xizmati o'qiydi, Admin API yozadi)
SET url:aB3xK9 "https://example.com/long/url" EX 86400
# TTL: 24 soat, kesh miss bo'lganda DB dan qayta yuklanadi

# URL Metadata (muddati tugash, parol tekshiruvi)
HSET url:meta:aB3xK9
  domain "go.brand.uz"
  expires_at "2026-12-31T23:59:59Z"
  has_password "1"
  is_active "1"
  max_clicks "1000"

# Real-time Statistika (tez dashboard uchun)
HINCRBY stats:aB3xK9 total 1
HINCRBY stats:aB3xK9 uz 1          # mamlakat kodi
HINCRBY stats:aB3xK9 mobile 1      # qurilma turi

# Rate Limiting (sliding window)
# 100 so'rov/daqiqa per IP, URL yaratish uchun
SET rate:192.168.1.1:create 1 EX 60
INCR rate:192.168.1.1:create
# Agar > 100 → HTTP 429

# API Kalit Kesh
HSET api_key:sha256_hash
  user_id "uuid"
  workspace_id "uuid"
  scopes "read,write"
  plan "pro"
  rate_limit "1000"

# Click Event Stream
XADD stream:clicks *
  code "aB3xK9"
  ts "1712345678000"
  ip "192.168.1.1"
  ua "Mozilla/5.0..."
  ref "https://twitter.com/..."
```

### Redis Konfiguratsiya

```conf
# redis.conf
maxmemory 4gb
maxmemory-policy allkeys-lfu        # LFU — ko'p botiladigan URLlar keshda qoladi

# Persistence (RDB + AOF)
save 900 1                           # 15 daqiqada 1 ta o'zgarish bo'lsa
save 300 10                          # 5 daqiqada 10 ta o'zgarish bo'lsa
appendonly yes
appendfsync everysec

# Streams sozlamalari
stream-node-max-bytes 4096
stream-node-max-entries 100
```

### Kesh Invalidatsiya Strategiyasi

```
URL Yaratilganda:
  1. PostgreSQL ga INSERT
  2. Redis ga SET url:{code} <long_url> EX 86400
  (Write-Through)

URL Yangilanganda:
  1. PostgreSQL da UPDATE
  2. Redis da DEL url:{code}  va  DEL url:meta:{code}
  (Cache Invalidation — keyingi redirect qayta yuklanadi)

URL O'chirilganda:
  1. PostgreSQL da soft delete (is_active = false)
  2. Redis da DEL url:{code}  va  DEL url:meta:{code}

Muddati Tugaganda:
  Redis TTL avtomatik o'chiradi, lekin muddati tugash tekshiruvi
  Go xizmatida ham bo'lishi kerak (url:meta dan expires_at tekshirish)
```

---

## 5. Message Queue va Event Processing

### Redis Streams (Tanlangan)

**Nega Redis Streams (RabbitMQ o'rniga):**
- Allaqachon Redis ishlatilmoqda — qo'shimcha infratuzilma yo'q
- Consumer Groups — bir nechta worker parallel ishlov berishi mumkin
- Persistence — hodisalar avtomatik diskka saqlanadi
- XACK — hodisa qayta ishlanganligi tasdiqlanadi, ishdan chiqishda qayta ishlov
- Oddiy — RabbitMQ ga qaraganda sozlash va boshqarish osonroq
- Throughput — sekundiga 100K+ message, ko'pchilik holatlar uchun yetarli

**Qachon RabbitMQ ga o'tish kerak:**
- Sekundiga 500K+ message
- Murakkab routing patterns kerak (topic exchange, dead letter queue)
- Bir nechta consumer turli xil ishlov berishi kerak

### Event Oqimi

```
Go Redirect Xizmati                    Redis Streams                Analytics Worker(s)
       │                                    │                              │
       │ XADD stream:clicks *               │                              │
       │ code=aB3xK9                        │                              │
       │ ts=1712345678                      │                              │
       │ ip=1.2.3.4                         │                              │
       │ ua=Mozilla/5.0...                  │                              │
       │ ref=https://twitter.com            │                              │
       │──────────────────────────────────▶│                              │
       │                                    │  XREADGROUP GROUP analytics  │
       │                                    │  CONSUMER worker-1           │
       │                                    │  COUNT 100                    │
       │                                    │  BLOCK 5000                   │
       │                                    │◀─────────────────────────────│
       │                                    │                              │
       │                                    │  [100 ta event qaytariladi]  │
       │                                    │─────────────────────────────▶│
       │                                    │                              │
       │                                    │                   Boyitish:  │
       │                                    │                   GeoIP      │
       │                                    │                   UA Parse   │
       │                                    │                   Bot check  │
       │                                    │                              │
       │                                    │                   Batch      │
       │                                    │                   INSERT →   │
       │                                    │                   ClickHouse │
       │                                    │                              │
       │                                    │  XACK stream:clicks          │
       │                                    │  analytics msg-id-1...       │
       │                                    │◀─────────────────────────────│
```

### Consumer Group Sozlamalari

```bash
# Consumer group yaratish
redis-cli XGROUP CREATE stream:clicks analytics $ MKSTREAM

# Worker qo'shish (har bir worker o'ziga tegishli eventlarni oladi)
# worker-1: XREADGROUP GROUP analytics CONSUMER worker-1 COUNT 100 BLOCK 5000 STREAMS stream:clicks >
# worker-2: XREADGROUP GROUP analytics CONSUMER worker-2 COUNT 100 BLOCK 5000 STREAMS stream:clicks >
```

---

## 6. Analitika Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌───────────┐
│ Go Redirect│──▶│  Redis   │──▶│   Analytics   │──▶│ ClickHouse│
│  Xizmati  │   │ Streams  │   │    Worker     │   │           │
│           │   │          │   │              │   │ Raw clicks │
│ Click     │   │ stream:  │   │ • GeoIP      │   │ Daily MV   │
│ event     │   │ clicks   │   │ • UA parse   │   │ Hourly MV  │
│ chiqarish │   │          │   │ • Bot detect │   │           │
└──────────┘    └──────────┘   │ • Batch      │   └─────┬─────┘
                                │   insert     │         │
                                └──────┬───────┘         │
                                       │                 │
                                       ▼                 ▼
                                ┌──────────┐    ┌──────────────┐
                                │  Redis   │    │   FastAPI     │
                                │ Stats    │    │ Analytics API │
                                │ Counter  │    │              │
                                │          │◀───│ Dashboard    │
                                │ Real-time│    │ so'rovlari   │
                                └──────────┘    └──────────────┘
```

### Analitika So'rov Misollari

```sql
-- Oxirgi 7 kunda bosishlar (ClickHouse)
SELECT
    toDate(clicked_at) AS day,
    count() AS clicks,
    uniqExact(ip_hash) AS unique_clicks
FROM clicks
WHERE short_code = 'aB3xK9'
  AND clicked_at >= now() - INTERVAL 7 DAY
  AND is_bot = 0
GROUP BY day
ORDER BY day;

-- Mamlakat bo'yicha taqsimot (Materialized View dan — tezroq)
SELECT
    country_code,
    sum(click_count) AS clicks,
    sum(unique_visitors) AS unique_clicks
FROM clicks_daily_mv
WHERE short_code = 'aB3xK9'
  AND day >= today() - 30
GROUP BY country_code
ORDER BY clicks DESC
LIMIT 10;

-- Qurilma taqsimoti
SELECT
    device_type,
    sum(click_count) AS clicks
FROM clicks_daily_mv
WHERE short_code = 'aB3xK9'
  AND day >= today() - 30
GROUP BY device_type;
```

---

## 7. API Dizayni

### Autentifikatsiya

```
Ikki yo'l:
1. JWT Token (brauzer/frontend uchun)
   Authorization: Bearer eyJhbGciOiJIUzI1NiI...
   
2. API Kalit (API klientlar uchun)
   X-API-Key: usk_a3BxK9mN2pQr5tUv...
```

#### JWT Oqimi

```
┌────────┐         ┌──────────┐         ┌──────────┐
│ Klient │         │ FastAPI  │         │PostgreSQL│
│        │         │          │         │          │
│ POST /auth/login │          │         │          │
│ {email, password}│          │         │          │
│─────────────────▶│          │         │          │
│                  │ password  │         │          │
│                  │ tekshirish│────────▶│          │
│                  │          │◀────────│          │
│                  │          │         │          │
│ { access_token,  │ JWT yaratish       │          │
│   refresh_token }│          │         │          │
│◀─────────────────│          │         │          │
│                  │          │         │          │
│ GET /api/v1/urls │          │         │          │
│ Authorization:   │          │         │          │
│ Bearer <token>   │          │         │          │
│─────────────────▶│ JWT tekshirish     │          │
│                  │ (lokal, DB kerak   │          │
│ { urls: [...] }  │  emas — tez!)      │          │
│◀─────────────────│          │         │          │
```

**JWT Sozlamalari:**
```
Access Token:  15 daqiqa TTL, HS256 yoki RS256
Refresh Token: 7 kun TTL, PostgreSQL da saqlash
Payload: { sub: user_id, workspace_id, plan, scopes, exp, iat }
```

### Rate Limiting

| Endpoint | Bepul | Pro | Business | Enterprise |
|---|---|---|---|---|
| `POST /urls` | 10/soat | 100/soat | 1,000/soat | 10,000/soat |
| `GET /analytics/*` | 30/daqiqa | 100/daqiqa | 500/daqiqa | Cheksiz |
| `POST /urls/bulk` | Yo'q | 50 URL/so'rov | 200 URL/so'rov | 1,000 URL/so'rov |
| **Redirect** | Cheksiz | Cheksiz | Cheksiz | Cheksiz |

### API Javob Formati

```json
// Muvaffaqiyat
{
  "success": true,
  "data": { ... },
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 150
  }
}

// Xato
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit oshib ketdi. 60 sekunddan keyin qayta urinib ko'ring.",
    "retry_after": 60
  }
}
```

---

## 8. Xavfsizlik Arxitekturasi

```
┌────────────────────────────────────────────────────────────┐
│                    XAVFSIZLIK QATLAMLARI                    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  TARMOQ QATLAMI:                                           │
│  ├── HTTPS (TLS 1.3) — Let's Encrypt / Cloudflare          │
│  ├── DDoS himoyasi — Cloudflare / AWS Shield                │
│  ├── IP bloklash — Nginx deny / fail2ban                    │
│  └── CORS — faqat ruxsat etilgan originlar                  │
│                                                             │
│  APPLICATION QATLAMI:                                       │
│  ├── Input validatsiya — Pydantic v2 (FastAPI)              │
│  ├── URL validatsiya — sxema whitelist (http/https)         │
│  ├── SQL injection — SQLAlchemy parametrlangan so'rovlar     │
│  ├── XSS — HTMLni escape qilish, CSP headerlar              │
│  ├── CSRF — SameSite cookie + CSRF token                    │
│  ├── Rate limiting — Redis asosida (token bucket)           │
│  └── Bot aniqlash — User-Agent filtrlash + challenge         │
│                                                             │
│  AUTENTIFIKATSIYA QATLAMI:                                  │
│  ├── JWT (RS256) — access + refresh token                   │
│  ├── API kalitlar — SHA-256 xeshlangan, scoped              │
│  ├── Parol — bcrypt (cost=12)                               │
│  └── API kalit rotatsiya — muddati tugash + yangilash       │
│                                                             │
│  MA'LUMOTLAR QATLAMI:                                       │
│  ├── Parollar bcrypt bilan xeshlangan                       │
│  ├── API kalitlar SHA-256 bilan xeshlangan                  │
│  ├── IP manzillar xeshlangan (analitikada)                  │
│  ├── PII minimal — faqat kerakli ma'lumotlar                │
│  └── Ma'lumotlarni shifrlash (at rest + in transit)         │
│                                                             │
│  URL XAVFSIZLIGI:                                          │
│  ├── Google Safe Browsing API — yaratishda + davriy scan    │
│  ├── URL sxema whitelist — faqat http:// va https://        │
│  ├── Redirect loop aniqlash — o'z domeniga qaytmaslik       │
│  ├── Uzunlik cheklash — max 10,000 belgi                    │
│  ├── Maxsus belgilar sanitizatsiya — CRLF injection himoya  │
│  └── Foydalanuvchi hisoboti — zararli link xabar berish     │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 9. Infratuzilma va DevOps

### Docker Compose (Ishlab chiqish muhiti)

```yaml
# docker-compose.yml
version: '3.9'

services:
  # ============ XIZMATLAR ============
  
  redirect:
    build: ./services/redirect
    ports:
      - "8080:8080"
    environment:
      - REDIS_URL=redis://redis-cache:6379/0
      - REDIS_STREAM_URL=redis://redis-app:6380/0
      - PG_DSN=postgresql://user:pass@postgres:5432/urlshortener
    depends_on:
      - redis-cache
      - redis-app
      - postgres
    deploy:
      resources:
        limits:
          memory: 128M

  api:
    build: ./services/api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/urlshortener
      - REDIS_CACHE_URL=redis://redis-cache:6379/0
      - REDIS_APP_URL=redis://redis-app:6380/0
      - CLICKHOUSE_URL=clickhouse://clickhouse:9000/analytics
      - JWT_SECRET=your-secret-key
      - SAFE_BROWSING_API_KEY=your-key
    depends_on:
      - postgres
      - redis-cache
      - redis-app
      - clickhouse

  analytics-worker:
    build: ./services/analytics-worker
    environment:
      - REDIS_STREAM_URL=redis://redis-app:6380/0
      - CLICKHOUSE_URL=clickhouse://clickhouse:9000/analytics
      - GEOIP_DB_PATH=/data/GeoLite2-City.mmdb
    volumes:
      - geoip-data:/data
    depends_on:
      - redis-app
      - clickhouse
    deploy:
      replicas: 2  # 2 worker parallel ishlaydi

  frontend:
    build: ./services/frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost/api

  # ============ INFRATUZILMA ============
  
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - redirect
      - api
      - frontend

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=urlshortener
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"

  redis-cache:
    image: redis:7.2-alpine
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lfu
    ports:
      - "6379:6379"
    volumes:
      - redis-cache-data:/data

  redis-app:
    image: redis:7.2-alpine
    command: redis-server --port 6380 --appendonly yes
    ports:
      - "6380:6380"
    volumes:
      - redis-app-data:/data

  clickhouse:
    image: clickhouse/clickhouse-server:24-alpine
    ports:
      - "8123:8123"   # HTTP
      - "9000:9000"   # Native
    volumes:
      - clickhouse-data:/var/lib/clickhouse
      - ./clickhouse/init.sql:/docker-entrypoint-initdb.d/init.sql

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports:
      - "9002:9000"   # S3 API
      - "9001:9001"   # Console UI
    environment:
      - MINIO_ROOT_USER=minioadmin
      - MINIO_ROOT_PASSWORD=minioadmin
    volumes:
      - minio-data:/data

  geoip-updater:
    image: maxmindinc/geoipupdate
    environment:
      - GEOIPUPDATE_ACCOUNT_ID=${GEOIP_ACCOUNT_ID}
      - GEOIPUPDATE_LICENSE_KEY=${GEOIP_LICENSE_KEY}
      - GEOIPUPDATE_EDITION_IDS=GeoLite2-City
      - GEOIPUPDATE_FREQUENCY=168     # har hafta yangilash
    volumes:
      - geoip-data:/usr/share/GeoIP

  # ============ MONITORING ============
  
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana

volumes:
  postgres-data:
  redis-cache-data:
  redis-app-data:
  clickhouse-data:
  grafana-data:
  geoip-data:
  minio-data:
```

### Nginx Konfiguratsiya

```nginx
# nginx.conf
upstream redirect_service {
    server redirect:8080;
    # Bir nechta instansiya bo'lganda:
    # server redirect-1:8080;
    # server redirect-2:8080;
}

upstream api_service {
    server api:8000;
}

upstream frontend_service {
    server frontend:3000;
}

server {
    listen 80;
    server_name qisqa.uz *.qisqa.uz;

    # Frontend (Dashboard)
    location /dashboard {
        proxy_pass http://frontend_service;
    }

    location /_next {
        proxy_pass http://frontend_service;
    }

    # API
    location /api/ {
        proxy_pass http://api_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Rate limiting (Nginx darajasi)
        limit_req zone=api burst=20 nodelay;
    }

    # Swagger/OpenAPI docs
    location /docs {
        proxy_pass http://api_service;
    }

    location /redoc {
        proxy_pass http://api_service;
    }

    # Health checks
    location /health {
        proxy_pass http://api_service;
    }

    # REDIRECT — boshqa barcha yo'llar Go xizmatiga
    # Bu OXIRGI location bo'lishi kerak
    location / {
        # Agar bosh sahifa bo'lsa — frontend ga
        # Agar /{code} bo'lsa — redirect xizmatiga
        
        # Regex: 1-10 alfanumerik belgi — redirect
        location ~ ^/([a-zA-Z0-9_-]{1,10})$ {
            proxy_pass http://redirect_service;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            
            # Kesh headerlari
            proxy_hide_header Cache-Control;
            add_header Cache-Control "no-cache, no-store, must-revalidate";
        }
        
        # Bosh sahifa — frontend
        proxy_pass http://frontend_service;
    }
}

# Rate limiting zonalari
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
```

---

## 10. Monitoring va Observability

### Monitoring Steki

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Prometheus  │────▶│   Grafana    │     │   Sentry     │
│  (Metrikalar)│     │ (Dashboard)  │     │  (Xatolar)   │
└──────┬───────┘     └──────────────┘     └──────────────┘
       │
       │ scrape
       │
┌──────▼───────┐  ┌──────────────┐  ┌──────────────┐
│ Go Redirect  │  │ FastAPI API  │  │   Analytics  │
│ /metrics     │  │ /metrics     │  │    Worker    │
│              │  │              │  │   /metrics   │
│ • req/s      │  │ • req/s      │  │ • events/s   │
│ • latency    │  │ • latency    │  │ • queue lag  │
│ • cache hit% │  │ • errors     │  │ • batch size │
│ • goroutines │  │ • active req │  │ • CH latency │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Asosiy Metrikalar

| Metrika | Xizmat | Ogohlantirish Chegarasi |
|---|---|---|
| `redirect_requests_total` | Go Redirect | - |
| `redirect_latency_p99` | Go Redirect | > 50ms |
| `redirect_cache_hit_ratio` | Go Redirect | < 80% |
| `redirect_errors_total` | Go Redirect | > 10/daqiqa |
| `api_requests_total` | FastAPI | - |
| `api_latency_p99` | FastAPI | > 500ms |
| `api_errors_5xx_total` | FastAPI | > 5/daqiqa |
| `analytics_queue_lag` | Worker | > 10,000 events |
| `analytics_events_processed` | Worker | < 100/sek |
| `postgres_connections_active` | PostgreSQL | > 150 |
| `redis_memory_used` | Redis | > 80% max |
| `redis_cache_hit_ratio` | Redis | < 85% |
| `clickhouse_insert_rows` | ClickHouse | - |

### Logging

```
Tizim: Structured JSON Logging

Go:     zerolog yoki zap
Python: structlog
Format: {
  "timestamp": "2026-04-08T12:00:00Z",
  "level": "info",
  "service": "redirect",
  "method": "GET",
  "path": "/aB3xK9",
  "status": 302,
  "latency_ms": 2.3,
  "cache_hit": true,
  "request_id": "uuid"
}

To'plash: Loki (Grafana Loki) yoki ELK Stack
```

---

## 11. Joylashtirish Arxitekturasi

### Ishlab chiqish muhiti (Mahalliy)
```
Docker Compose — barcha xizmatlar bitta buyruq bilan
$ docker compose up -d
```

### Staging / Ishlab chiqarish

```
Variant A: VPS/Cloud VM (Oddiy, arzon — POC uchun tavsiya)
┌─────────────────────────────────────────┐
│              VM (4 CPU, 8GB RAM)          │
│                                          │
│  Docker Compose                          │
│  ├── Nginx                               │
│  ├── Go Redirect (×2 instansiya)         │
│  ├── FastAPI (×2 instansiya)             │
│  ├── Analytics Worker (×2)               │
│  ├── PostgreSQL                          │
│  ├── Redis (×2: cache + app)             │
│  ├── ClickHouse                          │
│  ├── Prometheus + Grafana                │
│  └── Frontend                            │
│                                          │
│  Narx: ~$20-50/oy (Hetzner/DigitalOcean)│
└─────────────────────────────────────────┘

Variant B: Kubernetes (Katta masshtab)
┌─────────────────────────────────────────┐
│          Kubernetes Cluster               │
│                                          │
│  Namespace: url-shortener                │
│  ├── Deployment: redirect (3-10 pod)     │
│  ├── Deployment: api (2-5 pod)           │
│  ├── Deployment: worker (2-4 pod)        │
│  ├── Deployment: frontend (2 pod)        │
│  ├── StatefulSet: postgres (1 primary    │
│  │   + 2 replica)                        │
│  ├── StatefulSet: redis-cache (3 node    │
│  │   cluster)                            │
│  ├── StatefulSet: redis-app (1 node)     │
│  ├── StatefulSet: clickhouse (1-3 node)  │
│  ├── Ingress: Nginx Ingress Controller   │
│  ├── HPA: auto-scaling redirect/api      │
│  └── CronJob: kgs-refill, url-cleanup    │
│                                          │
│  Narx: ~$100-500/oy (cloud provider)     │
└─────────────────────────────────────────┘
```

### CI/CD Pipeline

```
GitHub Actions:

Push to main:
  1. Lint + Test (Go: golangci-lint, pytest: Python)
  2. Build Docker images
  3. Push to Container Registry (GHCR / Docker Hub)
  4. Deploy to Staging (auto)
  5. Integration tests
  6. Deploy to Production (manual approval)

PR:
  1. Lint + Test
  2. Preview deployment (ixtiyoriy)
```

---

## 12. Texnologiyalar To'liq Ro'yxati

### Asosiy Xizmatlar

| Texnologiya | Versiya | Maqsad | Nega Tanlandi |
|---|---|---|---|
| **Go** | 1.22+ | Redirect xizmati | Eng tez, goroutinelar, kichik binary |
| **Fiber** | v3 (yoki v2.52+ stable) | Go HTTP framework | fasthttp ustiga qurilgan, Express-ga o'xshash API. v3 yangi router va yaxshilangan ishlash |
| **go-redis** | v9 (`github.com/redis/go-redis/v9`) | Go Redis klient | Connection pooling, pipeline, rasmiy Redis org ostida |
| **pgx** | v5 | Go PostgreSQL driver | Eng tez Go PG driver, native protocol |
| **geoip2-golang** | latest | GeoIP (Go) | MaxMind GeoLite2, xotirada ~1-5 mikrosekund qidirish |
| **Python** | 3.12+ | Admin API, Analytics Worker | Keng ekotizim, tez prototiplash |
| **FastAPI** | 0.115+ | Python web framework | Async, auto-docs, Pydantic v2 to'liq qo'llab-quvvatlash |
| **Uvicorn** | 0.29+ | ASGI server | uvloop bilan yuqori samaradorlik |
| **SQLAlchemy** | 2.0+ (`asyncpg` driver bilan) | Python ORM | Async qo'llab-quvvatlash, `create_async_engine` |
| **Alembic** | 1.13+ | DB migratsiya | Async engine qo'llab-quvvatlash (1.12+) |
| **Pydantic** | v2 | Ma'lumot validatsiya | Rust-core bilan 5-50x tezroq, `model_dump()` yangi API |
| **Next.js** | 14+ | Frontend framework | App Router, SSR, ajoyib DX |
| **React** | 18+ | UI kutubxona | Komponent-asoslangan, keng ekotizim |
| **Tailwind CSS** | 3.4+ | CSS framework | Utility-first, tez styling |
| **shadcn/ui** | latest | UI komponentlar | Chiroyli, accessible, sozlanuvchi |

### Ma'lumotlar Qatlami

| Texnologiya | Versiya | Maqsad | Nega Tanlandi |
|---|---|---|---|
| **PostgreSQL** | 17+ (18 mavjud) | Asosiy RDBMS | ACID, yetuk, yaxshilangan partitsiya pruning (17+) |
| **Redis / Valkey** | 7.2+ | Kesh + Queue + Session | LFU, Streams, yuqori samaradorlik. **Eslatma:** Redis 7.4+ litsenziya o'zgardi (RSALv2+SSPL). O'z-o'zi joylashtirish uchun **Valkey** (Linux Foundation fork, to'liq ochiq manba, API-mos) ko'rib chiqing |
| **ClickHouse** | 24+ (25.x mavjud) | Analitika bazasi | Ustun-yo'naltirilgan, siqish, tez so'rovlar |
| **PgBouncer** | 1.22+ | Connection pooling | PostgreSQL ulanish havzasi (transaction mode) |
| **MinIO** | latest | Obyekt saqlash (S3-mos) | QR kod rasmlari va eksportlar uchun |

### DevOps va Infratuzilma

| Texnologiya | Maqsad | Nega Tanlandi |
|---|---|---|
| **Docker** | Konteynerlashtirish | Standart, barcha muhitlarda bir xil |
| **Docker Compose** | Mahalliy orkestratsiya | Oddiy, bitta fayl |
| **Nginx** | Reverse proxy + LB | Ishonchli, tez, yetuk. POC uchun tavsiya. Keyinchalik Traefik (auto-discovery, auto-TLS) ko'rib chiqish |
| **GitHub Actions** | CI/CD | GitHub bilan integratsiya, bepul daqiqalar |
| **Let's Encrypt** | SSL sertifikat | Bepul, avtomatik yangilanish |
| **MinIO** | Obyekt saqlash (S3-mos) | QR kod rasmlari saqlash, bepul, o'z-o'zini joylashtirish |
| **MaxMind GeoLite2** | IP geolokatsiya | Bepul (ro'yxatdan o'tish kerak), haftalik yangilanish, `.mmdb` fayl |

### Monitoring va Logging

| Texnologiya | Maqsad |
|---|---|
| **Prometheus** | Metrika to'plash |
| **Grafana** | Dashboard va vizualizatsiya |
| **Sentry** | Xato kuzatish (Go + Python) |
| **zerolog** (Go) / **structlog** (Python) | Structured logging |
| **Grafana Loki** | Log agregatsiya (ixtiyoriy) |

### Yordamchi Kutubxonalar

| Kutubxona | Til | Maqsad |
|---|---|---|
| **geoip2** | Python | MaxMind GeoLite2 IP geolokatsiya |
| **ua-parser** | Python | User-Agent tahlili |
| **qrcode + Pillow** | Python | QR kod generatsiya |
| **python-jose** | Python | JWT token yaratish/tekshirish |
| **bcrypt** | Python | Parol xeshlash |
| **httpx** | Python | Async HTTP klient (webhook, URL tekshirish) |
| **clickhouse-connect** | Python | ClickHouse klient |
| **aioredis / redis-py** | Python | Async Redis klient |
| **prometheus_client** | Python | Prometheus metrikalar |
| **gofiber/contrib** | Go | Fiber middleware (prometheus, cors, limiter) |
| **google/safebrowsing** | Go/Python | URL xavfsizlik tekshirish |

---

## 13. Papka Tuzilmasi

```
url-shortener/
│
├── services/
│   ├── redirect/                    # Go Redirect Xizmati
│   │   ├── cmd/
│   │   │   └── main.go             # Entry point
│   │   ├── internal/
│   │   │   ├── handler/
│   │   │   │   └── redirect.go     # GET /{code} handler
│   │   │   ├── cache/
│   │   │   │   └── redis.go        # Redis kesh operatsiyalari
│   │   │   ├── store/
│   │   │   │   └── postgres.go     # DB fallback qidirish
│   │   │   ├── events/
│   │   │   │   └── publisher.go    # Redis Streams ga event chiqarish
│   │   │   └── config/
│   │   │       └── config.go       # Konfiguratsiya
│   │   ├── Dockerfile
│   │   ├── go.mod
│   │   └── go.sum
│   │
│   ├── api/                         # FastAPI Admin API
│   │   ├── app/
│   │   │   ├── main.py             # FastAPI app yaratish
│   │   │   ├── config.py           # Sozlamalar (pydantic-settings)
│   │   │   ├── database.py         # SQLAlchemy async engine
│   │   │   ├── dependencies.py     # Dependency injection
│   │   │   │
│   │   │   ├── models/             # SQLAlchemy modellari
│   │   │   │   ├── user.py
│   │   │   │   ├── url.py
│   │   │   │   ├── domain.py
│   │   │   │   ├── api_key.py
│   │   │   │   └── webhook.py
│   │   │   │
│   │   │   ├── schemas/            # Pydantic sxemalari
│   │   │   │   ├── url.py
│   │   │   │   ├── user.py
│   │   │   │   ├── analytics.py
│   │   │   │   └── common.py
│   │   │   │
│   │   │   ├── routers/            # API endpointlar
│   │   │   │   ├── urls.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── analytics.py
│   │   │   │   ├── domains.py
│   │   │   │   ├── api_keys.py
│   │   │   │   ├── webhooks.py
│   │   │   │   └── qr.py
│   │   │   │
│   │   │   ├── services/           # Biznes logika
│   │   │   │   ├── url_service.py
│   │   │   │   ├── auth_service.py
│   │   │   │   ├── analytics_service.py
│   │   │   │   ├── domain_service.py
│   │   │   │   ├── kgs_service.py      # Key Generation Service
│   │   │   │   ├── safe_browsing.py    # URL xavfsizlik tekshirish
│   │   │   │   └── webhook_service.py
│   │   │   │
│   │   │   ├── middleware/
│   │   │   │   ├── rate_limiter.py
│   │   │   │   ├── auth.py
│   │   │   │   └── logging.py
│   │   │   │
│   │   │   └── utils/
│   │   │       ├── base62.py           # Base62 encode/decode
│   │   │       ├── url_validator.py    # URL validatsiya
│   │   │       └── hash.py            # Xeshlash utillar
│   │   │
│   │   ├── alembic/                # DB migratsiyalar
│   │   │   └── versions/
│   │   ├── alembic.ini
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── analytics-worker/            # Analytics Worker
│   │   ├── worker/
│   │   │   ├── main.py             # Entry point
│   │   │   ├── consumer.py         # Redis Streams consumer
│   │   │   ├── enricher.py         # GeoIP + UA boyitish
│   │   │   ├── writer.py           # ClickHouse batch yozish
│   │   │   └── bot_detector.py     # Bot aniqlash
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   └── frontend/                    # Next.js Frontend
│       ├── src/
│       │   ├── app/                 # App Router sahifalari
│       │   ├── components/          # React komponentlar
│       │   ├── hooks/               # Custom hooklar
│       │   ├── lib/                 # Yordamchi funksiyalar
│       │   └── styles/              # Tailwind sozlamalari
│       ├── package.json
│       └── Dockerfile
│
├── nginx/
│   └── nginx.conf                   # Reverse proxy konfiguratsiya
│
├── db/
│   └── init.sql                     # PostgreSQL boshlang'ich sxema
│
├── clickhouse/
│   └── init.sql                     # ClickHouse boshlang'ich sxema
│
├── monitoring/
│   ├── prometheus.yml               # Prometheus konfiguratsiya
│   └── grafana/
│       └── dashboards/              # Grafana dashboard JSON
│
├── docker-compose.yml               # Barcha xizmatlar
├── docker-compose.prod.yml          # Production overrides
├── Makefile                         # Foydali buyruqlar
├── .env.example                     # Muhit o'zgaruvchilari namuna
├── .github/
│   └── workflows/
│       ├── ci.yml                   # Test + Lint
│       └── deploy.yml               # Deploy pipeline
│
└── research/                        # Tadqiqot hujjatlari (mavjud)
    ├── 00-umumiy-xulosa.md
    ├── 01-arxitektura-va-system-design.md
    ├── 02-biznes-logika-va-funksiyalar.md
    ├── 03-arxitekturaviy-qarorlar-va-tradeofflar.md
    └── 04-ochiq-kodli-yechimlar.md
```

---

## 14. Ma'lumot Oqimi Diagrammalari

### URL Yaratish Oqimi

```
Klient           Nginx          FastAPI API        PostgreSQL       Redis
  │                │                │                 │               │
  │ POST /api/v1/urls              │                 │               │
  │ {url, custom_slug?}            │                 │               │
  │───────────────▶│               │                 │               │
  │                │──────────────▶│                 │               │
  │                │               │                 │               │
  │                │               │  1. URL validatsiya             │
  │                │               │  2. Safe Browsing tekshirish    │
  │                │               │  3. Normalizatsiya              │
  │                │               │  4. Deduplikatsiya tekshiruvi   │
  │                │               │────────────────▶│               │
  │                │               │◀────────────────│               │
  │                │               │                 │               │
  │                │               │  5. Qisqa kod olish (KGS pool) │
  │                │               │────────────────▶│               │
  │                │               │◀────────────────│               │
  │                │               │                 │               │
  │                │               │  6. URL saqlash                 │
  │                │               │────────────────▶│               │
  │                │               │◀────────────────│               │
  │                │               │                 │               │
  │                │               │  7. Redis keshga yozish         │
  │                │               │───────────────────────────────▶│
  │                │               │                 │               │
  │                │               │  8. Javob qaytarish             │
  │  {"short_url": "q.uz/aB3xK9"} │                 │               │
  │◀───────────────│◀──────────────│                 │               │
```

### Redirect + Analitika Oqimi

```
Klient     Nginx     Go Redirect    Redis Cache    Redis Stream    Worker    ClickHouse
  │          │            │              │              │             │           │
  │GET /aB3xK9           │              │              │             │           │
  │─────────▶│           │              │              │             │           │
  │          │──────────▶│              │              │             │           │
  │          │           │  GET url:aB3xK9             │             │           │
  │          │           │─────────────▶│              │             │           │
  │          │           │◀─────────────│              │             │           │
  │          │           │              │              │             │           │
  │          │           │  XADD stream:clicks          │             │           │
  │          │           │  (asinxron — redirect        │             │           │
  │          │           │   kutmaydi)                  │             │           │
  │          │           │────────────────────────────▶│             │           │
  │          │           │              │              │             │           │
  │ 302 Location: uzun-url.com         │              │             │           │
  │◀─────────│◀──────────│              │              │             │           │
  │          │           │              │              │             │           │
  │          │           │              │              │  XREADGROUP │           │
  │          │           │              │              │◀────────────│           │
  │          │           │              │              │             │           │
  │          │           │              │              │  events     │           │
  │          │           │              │              │────────────▶│           │
  │          │           │              │              │             │ GeoIP     │
  │          │           │              │              │             │ UA parse  │
  │          │           │              │              │             │ Bot check │
  │          │           │              │              │             │           │
  │          │           │              │              │             │ INSERT    │
  │          │           │              │              │             │──────────▶│
  │          │           │              │              │             │           │
  │          │           │              │              │  XACK       │           │
  │          │           │              │              │◀────────────│           │
```

---

## 15. Masshtablash Rejasi

### Faza 1: POC / MVP (0-10K users)

```
Bitta VPS (4 CPU, 8GB RAM, ~$20-40/oy)
├── Docker Compose
├── Bitta Go Redirect instansiya
├── Bitta FastAPI instansiya
├── PostgreSQL (bitta)
├── Redis (bitta, ikkala maqsad uchun)
├── ClickHouse (bitta)
└── O'tkazuvchanlik: ~5,000-10,000 redirect/sek
```

### Faza 2: O'sish (10K-100K users)

```
2-3 VPS + Managed DB
├── Load Balancer (Nginx / Cloud LB)
├── Go Redirect (×3 instansiya)
├── FastAPI (×2 instansiya)
├── Analytics Worker (×2)
├── PostgreSQL (managed, 1 primary + 1 replica)
├── Redis Cluster (3 node)
├── ClickHouse (bitta, kattaroq)
├── CDN (Cloudflare)
└── O'tkazuvchanlik: ~30,000-50,000 redirect/sek
```

### Faza 3: Masshtab (100K+ users)

```
Kubernetes Cluster
├── Go Redirect (×5-20 pod, HPA bilan)
├── FastAPI (×3-10 pod)
├── Analytics Worker (×4-8 pod)
├── PostgreSQL (shardlangan yoki Aurora/Cloud SQL)
├── Redis Cluster (6+ node)
├── ClickHouse Cluster (3+ node)
├── Kafka (Redis Streams o'rniga, >500K events/sek uchun)
├── Multi-region CDN
├── Global Load Balancing
└── O'tkazuvchanlik: 100,000+ redirect/sek
```

### Masshtablash Triggerlari

| Signal | Harakat |
|---|---|
| Redis kesh hit < 80% | Kesh hajmini oshirish yoki LFU sozlash |
| Go redirect P99 > 20ms | Instansiyalar qo'shish |
| PostgreSQL connections > 80% | PgBouncer qo'shish yoki read replica |
| Analytics queue lag > 10K | Worker instansiyalari qo'shish |
| ClickHouse so'rov > 5s | Materialized view qo'shish yoki shard |
| Umumiy redirect > 50K/sek | CDN edge caching yoqish |

---

## Xulosa

Bu HLA **Go + FastAPI gibrid arxitekturasi** asosida:

- **Go Redirect** — sub-5ms kechikish, 50K+ req/s bitta instansiya
- **FastAPI Admin** — tez prototiplash, boy ekotizim, auto-docs
- **PostgreSQL** — ishonchli asosiy baza, ACID kafolatlar
- **Redis** — 90%+ kesh hit, real-time counterlar, event queue
- **ClickHouse** — milliardlab bosishlarni sekundlarda tahlil
- **Docker Compose** — bitta buyruq bilan barcha xizmatlar

Bu arxitektura **POC dan ishlab chiqarishgacha** masshtablanishi mumkin — faqat instansiyalar sonini oshirish va managed xizmatlardan foydalanish kerak.
