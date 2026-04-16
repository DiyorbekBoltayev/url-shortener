# RV10 — Security & Production Hardening Audit

Scope: infrastructure, redirect-service, api-service, analytics-worker, admin-panel
Date: 2026-04-14

---

## 1. Security Blockers (must fix before prod deploy)

### 1.1 JWT_SECRET is a weak, committed placeholder
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\config.py:36`
`jwt_secret: SecretStr = SecretStr("dev-change-me-change-me-change-me-change-me")`
**File:** `C:\Users\User\Desktop\work\url-shortener\infrastructure\.env:44` — `JWT_SECRET=change_this_to_a_long_random_string_at_least_32_bytes`
`.env` is tracked (line exists in working tree, and is identical to `.env.example`).

Patch (`api-service/app/config.py:36`):
```python
jwt_secret: SecretStr  # required — no default. Fail-fast if unset.
```
Patch (`infrastructure/.env:44` & `api-service/.env:26`): delete the line. The placeholder belongs only in `.env.example`. Also run `git rm --cached .env` in every repo.

### 1.2 `.env` with real-ish secrets is present alongside `.env.example`
**Files:**
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\.env`
- `C:\Users\User\Desktop\work\url-shortener\api-service\.env`
- `C:\Users\User\Desktop\work\url-shortener\analytics-worker\.env`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\.env`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\.env`

Values `POSTGRES_PASSWORD=changeme_dev_only`, `MINIO_ROOT_PASSWORD=changeme_dev_only`, `GRAFANA_ADMIN_PASSWORD=admin`, `JWT_SECRET=change_this_...`, `WEBHOOK_SIGNING_KEY=change_this_webhook_signing_key` are **defaults that would ship to prod** unchanged. Add a hard startup check:

Patch (`api-service/app/config.py`, after `jwt_secret` line):
```python
@field_validator("jwt_secret")
@classmethod
def _reject_weak_jwt(cls, v: SecretStr) -> SecretStr:
    raw = v.get_secret_value()
    if len(raw) < 32 or "change" in raw.lower() or "dev-" in raw.lower():
        raise ValueError("JWT_SECRET must be >=32 random bytes (not a placeholder)")
    return v
```

### 1.3 No rate-limit bucket on `/auth/login` or `/auth/register`
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\middleware\rate_limiter.py:35-41`
`_match_bucket` covers only `POST /api/v1/urls` and `/api/v1/analytics`. Login falls into the default `rl_default_per_min=120` per-IP-per-path — plenty for credential stuffing. Nginx applies only `api:10r/s` (20 burst) at `infrastructure/nginx/nginx.conf:75,118` which is per-IP and easily bypassed from a botnet.

Patch (`rate_limiter.py:35`):
```python
def _match_bucket(path: str, method: str) -> tuple[str, int] | None:
    if method == "POST" and path.endswith("/api/v1/auth/login"):
        return ("auth_login", 60_000)         # 10/min per IP
    if method == "POST" and path.endswith("/api/v1/auth/register"):
        return ("auth_register", 3_600_000)   # 5/hour per IP
    if method == "POST" and path.endswith("/api/v1/urls"):
        return ("create_urls", 3_600_000)
    if path.startswith("/api/v1/analytics"):
        return ("analytics", 60_000)
    return None

_DEFAULT_LIMITS: dict[str, dict[str, int]] = {
    "auth_login":    {"free": 10, "pro": 10, "business": 10, "enterprise": 10},
    "auth_register": {"free": 5,  "pro": 5,  "business": 5,  "enterprise": 5},
    "create_urls":   {"free": 10, "pro": 100, "business": 1000, "enterprise": 10_000},
    "analytics":     {"free": 30, "pro": 100, "business": 500,  "enterprise": 1_000_000},
}
```
Also add a separate nginx `limit_req_zone auth:10m rate=5r/m;` and apply `limit_req zone=auth burst=5 nodelay;` to `location ~ ^/api/v1/auth/(login|register)$`.

### 1.4 Webhook SSRF — dispatch POSTs to arbitrary user-supplied URLs
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\services\webhook_service.py:37-50,104-106`
`create_webhook` stores any URL; `dispatch` then POSTs to it with `httpx.AsyncClient` over the container's network — can hit `http://postgres:5432`, `http://169.254.169.254/` (cloud metadata), `http://127.0.0.1:8000/`. `follow_redirects` default changes across httpx versions (safe now, but fragile).

Patch (new file `api-service/app/utils/safe_http.py` + use in `webhook_service.create_webhook`):
```python
import ipaddress, socket
from urllib.parse import urlparse

_BLOCKED_NETS = [ipaddress.ip_network(n) for n in
    ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","127.0.0.0/8",
     "169.254.0.0/16","::1/128","fc00::/7","fe80::/10")]

def assert_public_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in {"http", "https"} or not u.hostname:
        raise ValueError("only http(s) and a host are allowed")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except socket.gaierror as e:
        raise ValueError("dns resolution failed") from e
    for _, _, _, _, sa in infos:
        ip = ipaddress.ip_address(sa[0])
        if any(ip in net for net in _BLOCKED_NETS) or ip.is_multicast or ip.is_reserved:
            raise ValueError(f"refusing private/reserved address {ip}")
```
Call `assert_public_url(url)` in `create_webhook` *and* just before `client.post` in `dispatch` (DNS can change). Also pass `follow_redirects=False` to `httpx.AsyncClient`.

### 1.5 `/metrics` exposed on api-service/admin-panel without auth
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\main.py:82`
`Instrumentator().instrument(app).expose(app, endpoint="/metrics", ...)` — nginx blocks `/metrics` at the root but `/api/metrics` is NOT in the blocklist. Verify path: nginx currently blocks only `location = /metrics` (exact). The api-service is mounted under `/api/`, so `GET /api/metrics` is reachable externally and returns FastAPI's `/metrics` (via prefix-matched proxy).

Patch (`infrastructure/nginx/nginx.conf` inside the `server` block at line 115):
```nginx
location = /api/metrics     { return 403; }
location ~ ^/api/.*metrics$ { return 403; }  # defence in depth
```
And prefer to not expose at all: in `api-service/app/main.py:82` change endpoint to `/internal/metrics` and protect with an internal-only check or a shared-secret header.

### 1.6 CORS with `allow_credentials=True` + `allow_methods=["*"]` + `allow_headers=["*"]`
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\main.py:66-73`
This is valid because `cors_origins` is explicit (not `*`), but starlette *rejects* `credentials=True` with `origins=["*"]` only at runtime. Prevent accidental `CORS_ORIGINS="*"` from working:

Patch (`config.py`, add validator):
```python
@field_validator("cors_origins")
@classmethod
def _reject_star_origin(cls, v: list[str]) -> list[str]:
    if any(o.strip() == "*" for o in v):
        raise ValueError('CORS_ORIGINS must not be "*" when credentials are enabled')
    return v
```

### 1.7 Refresh tokens in `localStorage` — XSS == account takeover
**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\auth\auth.service.ts:18,43,51-52`
Comment acknowledges the tradeoff but there is no CSP on the root nginx to mitigate. This plus 1.8 below = a realistic XSS → full account compromise.

Patch: move refresh token to an `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` cookie. Backend change (`auth.py:82,95`): set/read cookie; `logout` clears it. If unwilling to rewrite the auth flow, add a rigid CSP (see 1.8).

### 1.8 No Content-Security-Policy header
**File:** `C:\Users\User\Desktop\work\url-shortener\infrastructure\nginx\nginx.conf:93-97`
Only `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-XSS-Protection` (obsolete). Missing `Content-Security-Policy`, `Strict-Transport-Security`, `Permissions-Policy` at the root.

Patch (`nginx.conf`, inside the `server` block):
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=(), payment=()" always;
```

### 1.9 Postgres / ClickHouse / Redis host ports exposed by default
**File:** `C:\Users\User\Desktop\work\url-shortener\infrastructure\docker-compose.yml:25-26,60-61,90-91,126-128`
Dev override publishes `5432:5432`, `6379:6379`, `6380:6380`, `8123:8123`, `9000:9000` to the host. `docker-compose.prod.yml` resets Postgres/Redis/ClickHouse (`ports: !reset []`), good — but **only when `-f docker-compose.prod.yml` is passed**. Easy to deploy dev compose by mistake.

Patch (`infrastructure/docker-compose.yml:25`): bind-only loopback:
```yaml
ports:
  - "127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432"
```
Repeat for redis-cache (line 60-61), redis-app (90-91), clickhouse (126-128). Defense in depth.

---

## 2. Hardening TODOs (should fix)

### 2.1 `analytics-worker` container runs as root stage copy is fine but user switch happens AFTER `COPY --chown` with root-owned venv
**File:** `C:\Users\User\Desktop\work\url-shortener\analytics-worker\Dockerfile:48`
`COPY --from=builder /opt/venv /opt/venv` keeps root ownership (the `--chown` is missing here). App files are chowned but venv is not; if the app tries to write to `/opt/venv` (pycache), it silently falls back in-memory or fails. Add `--chown=app:app`.

### 2.2 admin-panel nginx lacks CSP header (only helper SPA headers)
**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\nginx.conf:12-17`
Root nginx adds headers but the in-container nginx serves `/index.html` with its own response — add CSP here too (belt-and-braces), since the root proxy `add_header` is not duplicated if upstream sends its own headers for the same name.

### 2.3 admin-panel Dockerfile runs nginx as root
**File:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\Dockerfile:18-34`
Use `nginxinc/nginx-unprivileged:1.25-alpine` (runs as uid 101, listens on 8080), update `docker-compose.yml:13` `expose: - "8080"` and the root nginx `$admin_upstream` to `admin-panel:8080`.

### 2.4 TLS/443 block is commented-out only — no actual HSTS config path
**File:** `C:\Users\User\Desktop\work\url-shortener\infrastructure\nginx\nginx.conf:184-199`
Move the commented block into `conf.d/tls.conf.disabled` and add a clear opt-in. The current `add_header HSTS` would break plain-http dev. Gate HSTS:
```nginx
set $hsts "";
if ($scheme = https) { set $hsts "max-age=31536000; includeSubDomains"; }
add_header Strict-Transport-Security $hsts always;
```

### 2.5 Bulk create is NOT a transaction — partial success writes DB state
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\routers\urls.py:149-174`
Each iteration calls `url_service.create_url` which `db.flush()`s. On `Exception`, `get_session` dependency (`database.py:55`) will `rollback` everything on outer exception, but since we `except Exception` in the router, the session stays open and *commits* partial rows. Wrap each iteration in `async with db.begin_nested()` savepoints, or explicitly `await db.rollback()` inside the except.

### 2.6 No idempotency dedup on `POST /urls` (no md5 index lookup)
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\services\url_service.py:50-102`
`idx_urls_long_url_hash` exists in the migration (`md5(long_url)`) but is never used. A double-submit produces two distinct short codes for the same long URL. Optional but recommended — honor an `Idempotency-Key` header, or return existing short_code when `(user_id, md5(long_url))` matches within a 5-minute window.

### 2.7 `_merge_click_counts` imports inside the loop
**File:** `C:\Users\User\Desktop\work\url-shortener\api-service\app\routers\urls.py:56`
`from datetime import datetime, timezone` inside the `for` iteration — minor perf but also a code smell. Move to module scope.

### 2.8 Publisher queue drop metric is exposed — but no alert
**File:** `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\events\publisher.go:112`
Works correctly (non-blocking + `EventsDropped` counter + `EventsQueueDepth` gauge). No Prometheus alert rule defined for `rate(redirect_events_dropped_total[5m]) > 0`. Add an alert under `infrastructure/monitoring/`.

### 2.9 Analytics-worker DLQ forensic payload uses wrong key-flatten
**File:** `C:\Users\User\Desktop\work\url-shortener\analytics-worker\worker\pel_reclaimer.py:155-162`
`payload = dict(zip(flat[0::2], flat[1::2], strict=True))` always yields the same dict as `fields` (same source), just bytes-normalized. Functional, but simpler:
```python
payload = {k if isinstance(k, bytes) else str(k).encode():
           v if isinstance(v, bytes) else str(v).encode()
           for k, v in fields.items()}
payload[b"_orig_id"] = msg_id
```

### 2.10 ClickHouse default user with empty password
**File:** `C:\Users\User\Desktop\work\url-shortener\infrastructure\.env:35` — `CLICKHOUSE_PASSWORD=`
Comment warns about it. For prod, require non-empty and fail-fast in `analytics-worker/worker/config.py` and `api-service/app/config.py` when `environment="production"` and `clickhouse_password` is empty.

### 2.11 `fiberzerolog` logs full URL — short codes contain no PII but UA/ref may
**File:** `C:\Users\User\Desktop\work\url-shortener\redirect-service\cmd\server\main.go:144-147`
Fields `ip`, `ua` logged by default. GDPR concern. Either drop `ip` / hash it, or document the logging retention in the README.

### 2.12 Admin password for Grafana defaults to `admin/admin`
**File:** `C:\Users\User\Desktop\work\url-shortener\infrastructure\.env:60-61`
Change default fail-fast in compose: drop the `:-admin` fallback.
```yaml
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?must be set}
```

---

## 3. Nice-to-haves

- **JWT rotation:** `auth_service.logout` only revokes current access jti + deletes single refresh; sibling refresh tokens (e.g. other devices) survive. Add `revoke_all_sessions` that deletes `rt:{sub}:*` via `SCAN`.
- **Healthchecks:** admin-panel healthcheck `wget -q --spider http://localhost/` returns 200 even when the SPA is broken (nginx serves an empty page). Hit `/healthz` with a known response, or check `/index.html`.
- **Post-commit tests:** confirm `alembic upgrade head` on empty DB produces the same schema as `infrastructure/db/init.sql` (byte-for-byte diff via `pg_dump --schema-only`). The migration uses `CREATE EXTENSION IF NOT EXISTS` but table defs don't — `op.create_table` fails if the table exists.
- **Connection pools:** SQLAlchemy uses `pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=1800` (ok). Consider `pool_timeout=5` to surface saturation.
- **Argon2 params:** `pwdlib.PasswordHash.recommended()` uses sensible defaults. Document the cost factor in code and add a benchmark test to keep hash-time ~250–500 ms.
- **Short-code regex in redirect-service:** `^[a-zA-Z0-9_-]{1,10}$` allows single-char codes. If KGS guarantees >=3 chars, tighten the regex to `{3,10}` for defense-in-depth.
- **`proxy_pass http://$admin_upstream` lacks `X-Real-IP`/`XFF` for `/login`, `/register`, `/assets`** (`nginx.conf:145-148`). Consistency > headers not strictly required here.
- **Prefer `X-Content-Type-Options` via `sent_http_content_type` map** already present at line 79 but unused.
