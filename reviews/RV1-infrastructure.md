# RV1 — Infrastructure Review

**Reviewer:** RV1 (independent audit)
**Target:** `infrastructure/` (built by C1)
**Date:** 2026-04-14
**Scope:** Compose stack, Postgres/ClickHouse init, Nginx, Prometheus, Grafana, env, Makefile

---

## 1. Summary

**Status: PASS-WITH-FIXES**

`docker compose config` and `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` both parse cleanly (exit 0). Schemas, service names, ports, volume names and the external `url-shortener-net` network all conform to the Integration Contract.

Two correctness issues (MinIO healthcheck, Nginx healthcheck) and a handful of smaller gaps (no Prometheus persistence volume, tmpfs/ulimits missing on a few services, default Grafana credentials) are the only things blocking a clean merge. Nothing in the stack requires a re-architecture.

---

## 2. Contract conformance checklist

| Area | Contract requirement | Status | Evidence |
|---|---|---|---|
| Network name | `url-shortener-net`, bridge, subnet `172.28.0.0/16`, external | PASS | `docker-compose.yml:301-304`, `Makefile:7-8,32-35` |
| Service `postgres` | port 5432:5432, PG 17 | PASS | `docker-compose.yml:17-46` |
| Service `redis-cache` | port 6379:6379, no persistence | PASS | `docker-compose.yml:51-79` |
| Service `redis-app` | port 6380:6380 (internal 6380), AOF on | PASS | `docker-compose.yml:84-111` |
| Service `clickhouse` | ports 8123, 9000; db=analytics | PASS | `docker-compose.yml:116-150` |
| Service `minio` | host 9002:9000 (S3), 9001:9001 (console) | PASS | `docker-compose.yml:155-180` |
| Service `nginx` | 80, 443 to host | PASS | `docker-compose.yml:185-207` |
| Service `prometheus` | 9090 | PASS | `docker-compose.yml:212-235` |
| Service `grafana` | 3001:3000 | PASS | `docker-compose.yml:240-266` |
| Service `geoip-updater` | shared volume, no ports | PASS | `docker-compose.yml:271-283` |
| Volumes — explicit names (`urlshortener-*`) | use top-level `name:` field, no project prefix | PASS | `docker-compose.yml:285-299` |
| `geoip-data` volume | owner = infrastructure, named `urlshortener-geoip-data` | PASS | `docker-compose.yml:298-299`; consumers mount at `/data` per README |
| Nginx routing `/api/*` → api-service:8000 | variable-in-proxy_pass for DNS re-resolve | PASS | `nginx/nginx.conf:26-28, 117-130` |
| Nginx routing `/docs`, `/redoc`, `/openapi.json` → api-service | regex location | PASS | `nginx/nginx.conf:133-140` |
| Nginx routing `/{1-10 alnum}` → redirect-service:8080 | regex | PASS | `nginx/nginx.conf:144-164` |
| Nginx routing `/` and `/dashboard*` → admin-panel:80 | fallback location | PASS | `nginx/nginx.conf:167-174` |
| Nginx `/metrics` external → 403 | location block | PASS | `nginx/nginx.conf:112-114` |
| Prometheus scrape targets — service names on network | `redirect-service:8080/metrics`, `api-service:8000/metrics`, `analytics-worker:9091/metrics` | PASS | `monitoring/prometheus.yml:16-35` |
| Postgres schema — users, workspaces, workspace_members, domains, urls, api_keys, webhooks, short_code_pool | UUID + TIMESTAMPTZ, pgcrypto extension | PASS | `db/init.sql:1-210` |
| ClickHouse schema — `analytics.clicks` (MergeTree, PARTITION BY toYYYYMM, TTL 2y), `clicks_daily_mv`, `clicks_hourly_mv` (SummingMergeTree) | engines + ORDER BY | PASS | `clickhouse/init.sql:11-84` |
| Env convention — POSTGRES_DB / USER / PASSWORD, REDIS_CACHE_*, REDIS_APP_*, CLICKHOUSE_*, JWT_SECRET, MINIO_*, GEOIP_* | variable names match | PASS | `.env.example:7-53` |
| Resource limits per service | `deploy.resources.limits` | PASS | `docker-compose.yml` each service |
| JSON file log rotation (`max-size: 10m, max-file: 3`) | anchor `&default-logging` | PASS | `docker-compose.yml:7-11` |
| Prod override file merge (`docker-compose.prod.yml`) | removes ports for DBs, bumps limits, `restart: always` | PASS | `docker-compose.prod.yml:1-85` |
| `version:` key removed (Compose 2026 spec) | — | PASS | absent; both files use top-level `name:` instead |

Overall the stack aligns with the contract 1:1. The rest of this report covers what does NOT conform.

---

## 3. Blockers

### B1 — MinIO healthcheck command is not guaranteed to work in the image
**File:** `docker-compose.yml:168`
**Current:**
```yaml
test: ["CMD-SHELL", "mc ready local || curl -fsS http://127.0.0.1:9000/minio/health/live || exit 1"]
```
**Problem:** `minio/minio:latest` ships only the `minio` server binary. Neither `mc` nor `curl` is available inside the container, so both branches return "not found" and the probe reports `unhealthy` indefinitely. That does not kill the container (MinIO itself runs), but any `depends_on: { condition: service_healthy }` downstream will hang.
**Suggested fix:** use the built-in mc stub that the image DOES include (`readiness` check), or drop `mc` and use the curlless form:
```yaml
test: ["CMD-SHELL", "wget -q --spider http://127.0.0.1:9000/minio/health/live || exit 1"]
```
(The image does bundle BusyBox `wget`.)

### B2 — Nginx healthcheck is a syntax test, not a liveness probe
**File:** `docker-compose.yml:195`
**Current:**
```yaml
test: ["CMD", "nginx", "-t"]
```
**Problem:** `nginx -t` only validates the config file; it exits 0 even if the worker has crashed or is not accepting connections. A failed worker would still show as `healthy`. The `/healthz` endpoint at `nginx/nginx.conf:105-109` is exactly what the probe should hit.
**Suggested fix:**
```yaml
test: ["CMD-SHELL", "wget -q --spider http://127.0.0.1/healthz || exit 1"]
```

### B3 — `CLICKHOUSE_PASSWORD` is empty by default AND default access management is enabled
**File:** `docker-compose.yml:122-123`, `.env.example:31`
**Current:** `CLICKHOUSE_PASSWORD=` (empty) plus `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "1"`.
**Problem:** the `default` ClickHouse user is granted full RBAC admin with NO password. Because `clickhouse` is on the shared bridge network, anything on that network (including a compromised app container) gets superuser rights. The contract (§4) explicitly tolerates an empty password for dev, but in combination with `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1` this is a footgun even in dev. At minimum add a non-empty default in `.env.example` and document the requirement to change it.
**Suggested fix:** set `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "0"` unless explicitly needed, or require a password when it's `"1"`.

### B4 — `depends_on` missing for nginx → upstream-less infra
**File:** `docker-compose.yml:185-207` (nginx service)
**Problem:** nginx has no `depends_on`. The 4 app upstreams live in other compose projects so `depends_on: service_healthy` can't cross-project-reference them (that's fine, relies on `resolver` + variable-in-`proxy_pass`, correctly implemented), BUT within infra, Prometheus / Grafana / geoip-updater also have no dependency wiring:
- `grafana` should `depends_on: prometheus: { condition: service_healthy }` (dashboard provisioning reads from Prometheus at startup; if Prom isn't up, the datasource is marked dead until Grafana retries).
- `prometheus` does not need dependencies (it tolerates targets being absent).
**Suggested fix:** add
```yaml
grafana:
  depends_on:
    prometheus: { condition: service_healthy }
```
Not strictly required for the contract, but currently the intra-project `service_healthy` gates listed in `docker-multirepo.md` §6 are unused.

---

## 4. Nits

1. **No persistent volume for Prometheus** (`docker-compose.yml:212-235`). On restart, 30d retention is gone. Add `prometheus-data:/prometheus` — see research/tech/docker-multirepo.md §3 for the pattern.
2. **Grafana admin password defaults to `admin/admin`** (`.env.example:53`). The README says "change via `.env`" but doesn't enforce it. Either set a random default, or refuse to start when `GRAFANA_ADMIN_PASSWORD=admin`.
3. **No `ulimits` for postgres** — only ClickHouse has `nofile: 262144`. Postgres on a busy host benefits from the same.
4. **No `tmpfs: /tmp`** on any alpine container (redis-cache, redis-app, nginx). Marginal but listed in the docker-multirepo.md §7 prod-hardening checklist.
5. **`postgres-exporter` / `redis-exporter` / `nginx-exporter` are commented out** in `monitoring/prometheus.yml:37-45`. Leaving them off is fine for POC, but the compose file doesn't declare the exporters either — so when someone uncomments the scrape targets, Prometheus will just log failed scrapes. Either drop the comments or add the exporters.
6. **Log driver pinned to `json-file`** with 10m×3 rotation (`docker-compose.yml:7-11`). That's 30 MB/service worst-case — fine for dev — but in prod consider routing nginx access logs (JSON-structured already) to a side-car or `loki` driver for real retention.
7. **ClickHouse TTL** wraps `clicked_at` in `toDateTime()` (`clickhouse/init.sql:50`). The HLA spec (line 493) doesn't wrap. The conversion loses milliseconds but doesn't break TTL; still, leaving it as `clicked_at + INTERVAL 2 YEAR` is simpler.
8. **`redis-cache` has a volume mount** (`docker-compose.yml:63 urlshortener-redis-cache-data:/data`) but the command sets `--appendonly no --save ""`, i.e. no persistence is written. The volume exists but is always empty. Drop the mount.
9. **README service-plugging section for apps** mentions volume name `urlshortener-geoip-data` directly; contract §3 shows both a prefixed and non-prefixed form and says "we use the explicit name approach". Good — but the README's snippet at line 73 uses `urlshortener-geoip-data:` as the compose-local key, whereas apps usually prefer a short key (`geoip-data:`) that maps to the external name. Minor docs clarification.
10. **Nginx has no CORS headers**. Contract §4 sets `CORS_ORIGINS=http://localhost,http://admin-panel` — this is the api-service's responsibility per FastAPI middleware, but if the admin-panel ever serves from a different origin in prod (e.g. a CDN), CORS will need to be consolidated at nginx. Note for future.
11. **MinIO image is `:latest`** (`docker-compose.yml:156`) while every other service is pinned to a major/minor. The contract §12 doesn't list MinIO, so this is discretionary, but pinning prevents surprise breakage.
12. **`docker-compose.prod.yml` x-anchor duplication** — `x-prod-logging` is a clone of the dev `x-default-logging`. Could be imported via `extends:`/YAML merge, but Compose doesn't carry anchors across files; current duplication is the idiomatic workaround.

---

## 5. Security posture notes

- **Default dev credentials are present and explicit** (`POSTGRES_PASSWORD=changeme_dev_only`, `MINIO_ROOT_PASSWORD=changeme_dev_only`, `GF_SECURITY_ADMIN_PASSWORD=admin`, `JWT_SECRET=change_this_...`). All of them are in `.env.example` (committed) — **NOT** in `.env` (gitignored). This is correct. However, nothing in the stack refuses to start when an operator forgets to replace them. For prod, add a startup guard (entrypoint shim or Make target) that fails if `POSTGRES_PASSWORD == "changeme_dev_only"`.
- **`.env` is correctly gitignored** (`.gitignore:2-4`). `.dockerignore` also excludes it (`/.dockerignore:4-5`).
- **TLS is stubbed out** — the 443 server block in `nginx/nginx.conf:180-192` is commented. Dev only; prod deployment needs certs mounted at `/etc/nginx/certs/`. The `.gitignore:25` already excludes `nginx/certs/`.
- **`server_tokens off;`** is set (`nginx/nginx.conf:51`) — good, suppresses version disclosure.
- **Security headers** are added in the `server` block (`nginx/nginx.conf:94-97`): X-Content-Type-Options, X-Frame-Options, Referrer-Policy, X-XSS-Protection. Missing: `Strict-Transport-Security` (needs HTTPS first — deferred OK), `Content-Security-Policy` (recommended once admin-panel shape stabilizes).
- **Rate limits** are set for `/api/` (10r/s + burst 20) and redirects (100r/s + burst 200) — matches HLA §8 defaults.
- **`/metrics` is 403 externally**, internal scrape goes through Docker DNS on the shared network — correctly compartmentalized.
- **Postgres + Redis are exposed on localhost ports in dev** (5432/6379/6380/8123/9000). Prod override `!reset []` removes them (docker-compose.prod.yml:16, 29, 39, 49) — correct.
- **`CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "1"` with empty password** — see Blocker B3.

---

## 6. Integration risks (when the 4 app repos attach)

1. **nginx upstream resolution order.** Nginx starts before any app repo. Because of `resolver 127.0.0.11 valid=10s` + variable `proxy_pass`, the FIRST request to a missing upstream returns 502, subsequent ones recover within 10s. Acceptable per the contract, but make sure the orchestrator's smoke test retries at least twice.
2. **`geoip-data` volume consumers.** The infrastructure creates the volume as `urlshortener-geoip-data` at `/usr/share/GeoIP`. Apps must mount it as `external: true`, name `urlshortener-geoip-data`, path `/data:ro`. `GEOIP_DB_PATH=/data/GeoLite2-City.mmdb` in `.env.example` matches the consumer-side mount, NOT the updater-side. If any app accidentally mounts it at `/usr/share/GeoIP`, the env var path will be wrong. This is a contract-level fragility; the README at lines 70-81 does call out the `/data:ro` convention, good.
3. **analytics-worker `/metrics` port mismatch potential.** Contract §10 says `analytics-worker:9091/metrics` — `prometheus.yml:33` matches. If C4 accidentally exposes metrics on 9090 or 8000 instead, Prometheus will show the scrape as DOWN. No action for infra; flag for RV4.
4. **API CORS** — admin-panel serves from `/` under nginx, api-service under `/api/`. Same origin from the browser's point of view, so CORS is effectively bypassed. If admin-panel is deployed on a separate domain later, `CORS_ORIGINS` in api-service must be updated; nothing in infra enforces this.
5. **Postgres init.sql only runs on an empty volume.** If an existing `urlshortener-postgres-data` volume is present from a previous run, the schema changes in `db/init.sql` will NOT be reapplied. Any api-service migration strategy (Alembic per contract §12) must own ongoing schema evolution; the README needs a one-liner saying so (currently missing).
6. **ClickHouse init.sql also only runs on an empty volume.** The `make ch-init` Makefile target (`Makefile:70-72`) re-runs it manually — good mitigation, but not obvious to a newcomer.
7. **`depends_on: service_healthy` is a cross-project no-op.** Infrastructure can't gate apps and vice versa. The research doc's Makefile in §9 expects a root orchestrator Makefile to sequence `up-infra` → wait for healthchecks → `up-apps`. Only the per-repo Makefiles exist today; a root-level orchestrator Makefile is out of scope for C1 but should be owned by the orchestrator.
8. **redis-app has NO password.** The research doc (`docker-multirepo.md:149`) uses `--requirepass ${REDIS_APP_PASSWORD}`; C1's compose does not. Apps connecting with `redis://redis-app:6380/0` (no auth) will succeed, consistent with the contract (§4 has no `REDIS_APP_PASSWORD`), but this is a deviation from the research reference. Flagged for visibility, not a blocker because the contract overrides the research.

---

## Appendix — Files audited

- `C:\Users\User\Desktop\work\url-shortener\infrastructure\docker-compose.yml`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\docker-compose.prod.yml`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\.env.example`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\.gitignore`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\.dockerignore`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\Makefile`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\README.md`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\db\init.sql`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\clickhouse\init.sql`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\nginx\nginx.conf`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\nginx\conf.d\.gitkeep` (empty)
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\monitoring\prometheus.yml`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\monitoring\grafana\provisioning\datasources\prometheus.yml`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\monitoring\grafana\provisioning\dashboards\default.yml`
- `C:\Users\User\Desktop\work\url-shortener\infrastructure\monitoring\grafana\dashboards\url-shortener.json`

`docker compose config` (dev) — exit 0.
`docker compose -f docker-compose.yml -f docker-compose.prod.yml config` (prod merge) — exit 0.
