# Integration Contract — Multi-repo URL Shortener

> **Barcha 5 ta repo shu shartnomaga qat'iy rioya qilishi kerak.** Orkestrator (Claude) ma'qulladi. O'zgartirish faqat orkestrator orqali.

## 1. Shared Docker Network

**Nomi:** `url-shortener-net`
**Driver:** bridge
**Subnet:** `172.28.0.0/16`

**Oldindan yaratish (har bir compose dan oldin):**
```bash
docker network create --driver bridge --subnet 172.28.0.0/16 url-shortener-net
```

**Har bir docker-compose.yml faylda (infrastructure + 4 ta app):**
```yaml
networks:
  url-shortener-net:
    external: true
    name: url-shortener-net

services:
  <service-name>:
    networks:
      - url-shortener-net
```

---

## 2. Service nomlari va portlar (DNS)

Infrastructure compose quyidagilarni ta'minlaydi (boshqa repos shu nomlar bilan ulanadi):

| Service name (DNS) | Host port | Internal port | Maqsad |
|---|---|---|---|
| `postgres` | 5432 | 5432 | PostgreSQL 17 |
| `redis-cache` | 6379 | 6379 | URL kesh (db=0), session |
| `redis-app` | 6380 | 6380 | Streams (db=0), rate limit, stats |
| `clickhouse` | 8123, 9000 | 8123 (HTTP), 9000 (native) | Analytics |
| `minio` | 9002 (S3), 9001 (console) | 9000, 9001 | Obyekt saqlash |
| `nginx` | 80, 443 | 80, 443 | Reverse proxy |
| `prometheus` | 9090 | 9090 | Metrika |
| `grafana` | 3001 | 3000 | Dashboard |
| `geoip-updater` | — | — | MaxMind .mmdb yangilagich (shared volume) |

App servislari:
| Service name | Host port | Internal port | Maqsad |
|---|---|---|---|
| `redirect-service` | — (nginx orqali) | 8080 | Go redirect |
| `api-service` | — (nginx orqali) | 8000 | FastAPI admin |
| `analytics-worker` | — | — | Background worker |
| `admin-panel` | — (nginx orqali) | 80 | Angular SPA (nginx statik) |

Host port faqat `nginx` (80/443) va development uchun DB portlari. Prod da faqat nginx tashqariga chiqadi.

---

## 3. Shared volumes

| Volume nomi | Egasi | Foydalanuvchilar |
|---|---|---|
| `postgres-data` | infrastructure | — |
| `redis-cache-data` | infrastructure | — |
| `redis-app-data` | infrastructure | — |
| `clickhouse-data` | infrastructure | — |
| `minio-data` | infrastructure | — |
| `grafana-data` | infrastructure | — |
| `geoip-data` | infrastructure | analytics-worker, redirect-service (read-only mount) |

**Shared volume uchun har bir app compose:**
```yaml
volumes:
  geoip-data:
    external: true
    name: url-shortener_geoip-data   # infrastructure compose project prefix
```

**Alternative (afzal — aniq nom):** infrastructure compose da:
```yaml
volumes:
  geoip-data:
    name: urlshortener-geoip-data    # project prefix siz
```

Biz **aniq nom** yondashuvini ishlatamiz (prefix ishlatmaymiz).

---

## 4. Environment o'zgaruvchilari konvensiyasi

Har bir repo o'z `.env.example` faylini taqdim etadi. Root `.env.shared.example` umumiy sirlar uchun.

**Umumiy (barcha serveislar):**
```
# Postgres
POSTGRES_DB=urlshortener
POSTGRES_USER=ushortener
POSTGRES_PASSWORD=changeme_dev_only
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_CACHE_HOST=redis-cache
REDIS_CACHE_PORT=6379
REDIS_APP_HOST=redis-app
REDIS_APP_PORT=6380

# ClickHouse
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=9000
CLICKHOUSE_HTTP_PORT=8123
CLICKHOUSE_DB=analytics
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

# JWT
JWT_SECRET=change_this_to_a_long_random_string
JWT_ACCESS_TTL_MIN=15
JWT_REFRESH_TTL_DAYS=7

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=changeme_dev_only

# GeoIP (maxmind)
GEOIP_ACCOUNT_ID=
GEOIP_LICENSE_KEY=
GEOIP_DB_PATH=/data/GeoLite2-City.mmdb
```

**redirect-service qo'shimcha:**
```
PG_DSN=postgres://ushortener:changeme_dev_only@postgres:5432/urlshortener?sslmode=disable
REDIS_CACHE_URL=redis://redis-cache:6379/0
REDIS_STREAM_URL=redis://redis-app:6380/0
HTTP_PORT=8080
LOG_LEVEL=info
```

**api-service qo'shimcha:**
```
DATABASE_URL=postgresql+asyncpg://ushortener:changeme_dev_only@postgres:5432/urlshortener
REDIS_CACHE_URL=redis://redis-cache:6379/0
REDIS_APP_URL=redis://redis-app:6380/0
CLICKHOUSE_URL=clickhouse://default:@clickhouse:9000/analytics
CORS_ORIGINS=http://localhost,http://admin-panel
SAFE_BROWSING_API_KEY=
```

**analytics-worker qo'shimcha:**
```
REDIS_STREAM_URL=redis://redis-app:6380/0
CLICKHOUSE_URL=clickhouse://default:@clickhouse:9000/analytics
STREAM_NAME=stream:clicks
CONSUMER_GROUP=analytics
BATCH_SIZE=1000
FLUSH_INTERVAL_SEC=1
```

**admin-panel qo'shimcha:** (build-time)
```
API_BASE_URL=/api
```

---

## 5. Redis Streams shartnomasi

**Stream name:** `stream:clicks`
**Consumer group:** `analytics`
**Maxlen:** `MAXLEN ~ 1000000` (approximate trimming)

**Payload (XADD):**
```
XADD stream:clicks MAXLEN ~ 1000000 * \
  code <short_code> \
  ts <unix_ms> \
  ip <client_ip> \
  ua <user_agent> \
  ref <referer> \
  country <country_code>    # redirect-service da allaqachon GeoIP qilingan
```

---

## 6. Nginx routing qoidalari

```
/                       → admin-panel (landing / login / register SPA)
/dashboard, /dashboard/*→ admin-panel
/api/*                  → api-service:8000
/docs, /redoc, /openapi.json → api-service:8000
/metrics                → prometheus (faqat internal, external 403)
/{1-10 alnum}           → redirect-service:8080
```

---

## 7. HTTP status va javob formati

**API muvaffaqiyat:**
```json
{ "success": true, "data": { ... }, "meta": { "page": 1, "per_page": 20, "total": 150 } }
```

**API xato:**
```json
{ "success": false, "error": { "code": "RATE_LIMIT_EXCEEDED", "message": "...", "retry_after": 60 } }
```

**Redirect:** HTTP 302 Location: `<long_url>` (expired: 410, not found: 404, blocked: 451)

---

## 8. Healthcheck shartnomasi

Har bir xizmat `/health` (redirect, api) yoki `/-/healthy` (worker) endpoint taqdim etadi.

**Shakl:**
```json
{ "status": "ok", "checks": { "redis": "ok", "postgres": "ok" } }
```

HTTP 200 agar hammasi OK, 503 agar hech bo'lmaganda bittasi fail.

Docker healthcheck CMD:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 10s
  timeout: 3s
  retries: 3
  start_period: 20s
```

---

## 9. Logging

Barcha xizmatlar **JSON structured logs** chiqaradi stdout ga:
```json
{"time":"2026-04-14T12:00:00Z","level":"info","service":"redirect","msg":"redirect","code":"aB3xK9","latency_ms":2.3}
```

Go: zerolog. Python: structlog. Angular: console.log ok (prod da minimal).

---

## 10. Prometheus metrika endpointlari

Har bir service `/metrics` ochadi:
- redirect-service:8080/metrics
- api-service:8000/metrics
- analytics-worker:9091/metrics (alohida port)

Prometheus scrape config shu endpointlarni so'raydi.

---

## 11. Git repo holatiga tayyorlash

Har bir repo ichida:
- `.gitignore` (tilga xos + `.env`, `node_modules`, `__pycache__`, `dist/`, `build/`)
- `.env.example` (secretlarsiz)
- `README.md` (how to run locally + docker)
- `LICENSE` (MIT)
- `.dockerignore`
- `Makefile` (build, run, test, logs, down)

Foydalanuvchi keyin har birini `git init && git remote add origin ...` qiladi.

---

## 12. Versiyalar (qat'iy)

| Texnologiya | Versiya |
|---|---|
| Go | 1.22+ (Dockerfile base: `golang:1.23-alpine`) |
| Fiber | v2.52.9 |
| go-redis | v9.14.0 |
| pgx | v5.8.0 |
| Python | 3.12 (slim-bookworm) |
| FastAPI | 0.115+ |
| SQLAlchemy | 2.0.44 (asyncio) + asyncpg 0.30 |
| Pydantic | 2.11+ |
| PyJWT | 2.9+ (python-jose ISHLATILMAYDI — o'lik) |
| pwdlib | argon2/bcrypt (passlib ISHLATILMAYDI — o'lik) |
| redis-py | 5.2 (hiredis bilan) |
| clickhouse-connect | 0.8.10+ |
| ua-parser[regex] | 1.0.1 (user-agents ISHLATILMAYDI — tashlandiq) |
| Angular | 19.x (latest stable) |
| PrimeNG | 19.x |
| Tailwind | 3.4+ |
| Node | 20-alpine (build) |
| Postgres | 17-alpine |
| Redis | 7.2-alpine |
| ClickHouse | 24-alpine |
| Nginx | 1.25-alpine |
