# redirect-service

Go + Fiber v2 microservice that serves the URL shortener's hot path:

```
GET /{code}    → 302 Location: <long_url>   (or 404 / 410 / 451)
GET /health    → { status, checks: {...} }  (200 / 503)
GET /metrics   → Prometheus exposition
```

- Target latency: **p99 < 5 ms** on cache hit, < 20 ms on Postgres fallback
- Target throughput: 50k-100k req/s per pod
- Binary: ~15 MB on `distroless/static:nonroot`

Part of the multi-repo URL shortener. Conforms to `../INTEGRATION_CONTRACT.md`.

---

## Architecture

```
            ┌────────────┐     miss     ┌─────────────┐
 nginx ──▶  │  /:code    │ ───────────▶ │  Postgres   │
            │  handler   │              │ (urls tbl)  │
            │            │ ◀─ hit/set ──└─────────────┘
            │            │         ┌────────────────┐
            │            │ ───────▶│ redis-cache    │ (url:<code> → long_url)
            │            │         └────────────────┘
            │            │ ──XADD─▶┌────────────────┐
            │            │ (async) │ redis-app      │ (stream:clicks)
            └────────────┘         └────────────────┘
                 │
                 ├─ GeoIP: in-memory MaxMind .mmdb (1-5 µs lookup)
                 └─ Publisher: bounded channel (10 000) + 4 workers
```

**Flow per request (cache hit):**
1. Validate `code` against `^[a-zA-Z0-9_-]{1,10}$`.
2. `GET url:<code>` in `redis-cache` (~90% hit).
3. GeoIP lookup on `c.IP()` — in-process.
4. Non-blocking `XADD stream:clicks MAXLEN ~ 1000000 *` to `redis-app`. If the channel is full → drop + `redirect_events_dropped_total++`.
5. `302 Location: <long_url>` + `Cache-Control: no-store`.

**Fallback (cache miss):** 200 ms-timeout query against Postgres (`urls` table), populate cache, then serve (or 404 / 410 / 451).

---

## Folder layout

```
redirect-service/
├── cmd/server/main.go         # wiring only
├── internal/
│   ├── config/                # env parsing (caarlos0/env/v11)
│   ├── cache/                 # Redis cache-aside
│   ├── store/                 # pgxpool + URLLookup
│   ├── events/                # bounded channel → XADD workers
│   ├── geoip/                 # MaxMind wrapper (no-op fallback)
│   ├── handler/               # redirect + health
│   ├── metrics/               # prometheus collectors
│   └── middleware/            # request id
├── Dockerfile                 # multistage → distroless/static:nonroot
├── docker-compose.yml         # single service on url-shortener-net
├── go.mod
├── Makefile
├── .env.example
└── .golangci.yml
```

Test files live next to the code they cover (`*_test.go`).

---

## Run locally

Requires the `url-shortener-net` Docker network and the infrastructure stack (`postgres`, `redis-cache`, `redis-app`, `geoip-updater`) running from the sister `infrastructure` repo.

```bash
# one time
docker network create --driver bridge --subnet 172.28.0.0/16 url-shortener-net

# copy env and edit as needed
cp .env.example .env

# build + run
make docker-build
make up
curl -i http://localhost/aB3xK9   # via nginx
```

Without Docker (dev):

```bash
make tidy
export $(grep -v '^#' .env.example | xargs -d '\n')
# override hosts to localhost if infra is port-forwarded
export REDIS_CACHE_URL=redis://localhost:6379/0
export REDIS_STREAM_URL=redis://localhost:6380/0
export PG_DSN='postgres://ushortener:changeme_dev_only@localhost:5432/urlshortener?sslmode=disable'
make run
```

---

## Environment variables

| Variable                | Default                            | Notes                              |
|-------------------------|------------------------------------|------------------------------------|
| `HTTP_PORT`             | `8080`                             | Internal port                      |
| `LOG_LEVEL`             | `info`                             | `trace`…`error`                    |
| `LOG_FORMAT`            | `json`                             | `json` \| `console`                |
| `REDIS_CACHE_URL`       | *required*                         | `redis://redis-cache:6379/0`       |
| `REDIS_STREAM_URL`      | *required*                         | `redis://redis-app:6380/0`         |
| `REDIS_POOL_SIZE`       | `100`                              |                                    |
| `REDIS_MIN_IDLE_CONNS`  | `10`                               |                                    |
| `REDIS_READ_TIMEOUT_MS` | `200ms`                            | Tight — redirect budget            |
| `REDIS_WRITE_TIMEOUT_MS`| `200ms`                            |                                    |
| `PG_DSN`                | *required*                         |                                    |
| `PG_MIN_CONNS`          | `2`                                |                                    |
| `PG_MAX_CONNS`          | `20`                               | Per pod                            |
| `PG_QUERY_TIMEOUT_MS`   | `200ms`                            | Applied to URLLookup + Ping        |
| `GEOIP_DB_PATH`         | `/data/GeoLite2-City.mmdb`         | Missing → no-op reader (`XX`)      |
| `STREAM_NAME`           | `stream:clicks`                    | Contract §5                        |
| `STREAM_MAXLEN`         | `1000000`                          | Approx trim                        |
| `STREAM_WORKERS`        | `4`                                |                                    |
| `STREAM_BUFFER`         | `10000`                            | Channel depth                      |
| `CACHE_TTL_HIT`         | `24h`                              |                                    |
| `CACHE_TTL_MISS`        | `5m`                               | Negative cache                     |
| `SHUTDOWN_TIMEOUT`      | `30s`                              |                                    |
| `TRUST_PROXY`           | `true`                             | Honour `X-Forwarded-For` from nginx|
| `PROXY_HEADER`          | `X-Forwarded-For`                  |                                    |

---

## Metrics

All exposed on `/metrics`. Custom collectors live in `internal/metrics`:

| Metric                              | Type      | Labels   |
|-------------------------------------|-----------|----------|
| `redirect_requests_total`           | counter   | `status` |
| `redirect_latency_seconds`          | histogram | `status` |
| `redirect_cache_hits_total`         | counter   |          |
| `redirect_cache_misses_total`       | counter   |          |
| `redirect_pg_fallback_total`        | counter   |          |
| `redirect_events_published_total`   | counter   |          |
| `redirect_events_dropped_total`     | counter   |          |
| `redirect_events_failed_total`      | counter   |          |
| `redirect_events_queue_depth`       | gauge     |          |
| `redirect_errors_total`             | counter   | `source` |

Additionally fiberprometheus registers HTTP histograms under
`http_requests_*` (default registry).

Suggested alerts:

- `rate(redirect_events_dropped_total[1m]) > 0` → CRITICAL
- `histogram_quantile(0.99, rate(redirect_latency_seconds_bucket[5m])) > 0.005` → WARN
- `rate(redirect_errors_total{source="db"}[1m]) > 10` → CRITICAL

---

## Tests

```
make test          # unit tests (miniredis + pgxmock)
make test-race
make cover         # coverage.out + coverage.html
```

No real Docker is required — all Redis/Postgres interactions are faked
with `github.com/alicebob/miniredis/v2` and `github.com/pashagolub/pgxmock/v4`.

---

## Troubleshooting

**`x509: certificate signed by unknown authority` on outbound TLS** → the
distroless/static:nonroot image ships CA certs; verify with `ldd /app/redirect`
(should be static). If a custom CA is needed, mount it and set
`SSL_CERT_FILE`.

**`redis: client closed`** during shutdown → expected; `app.ShutdownWithContext`
cancels in-flight contexts (Fiber v2 known behaviour). The 30 s shutdown budget
covers the publisher drain.

**`geoip .mmdb not loaded`** → the service runs in a degraded mode returning
`country=XX`. Mount `urlshortener-geoip-data` or run the `geoip-updater`
sidecar.

**High `redirect_events_dropped_total`** → Redis streams are backpressuring.
Check `redis-app` CPU / `XLEN stream:clicks` and the analytics-worker lag.
Do NOT increase the buffer as a fix — fix the consumer.

---

## License

MIT — see `LICENSE`.
