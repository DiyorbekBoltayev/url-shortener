# Go Redirect Microservice — Reference Doc

**Scope:** Source-of-truth spec for the high-traffic redirect service (`GET /:shortcode` → 302 to long URL). Read-path-only; writes happen elsewhere (admin API).

**Last verified:** 2026-04-14

---

## 1. Recommended Versions (locked)

The project brief requires Go 1.22+ and Fiber **v2** (v3 is stable as of 2026-02 but the brief pins v2). We lock the minimum toolchain at Go 1.22 but build CI against Go 1.24 (current LTS-ish window — Go team supports the two latest minors; 1.24 + 1.25 are active, 1.26 is latest).

```
go 1.22

require (
    github.com/gofiber/fiber/v2                 v2.52.9
    github.com/redis/go-redis/v9                v9.14.0
    github.com/jackc/pgx/v5                     v5.8.0
    github.com/rs/zerolog                       v1.34.0
    github.com/prometheus/client_golang         v1.23.0
    github.com/oschwald/geoip2-golang           v1.11.0   // stay on v1 — v2 has breaking API changes
    github.com/ansrivas/fiberprometheus/v2      v2.10.1   // Fiber v2 Prom adapter
    github.com/caarlos0/env/v11                 v11.3.1   // 12-factor env loader
    github.com/testcontainers/testcontainers-go v0.38.0
)
```

**Pinning rules:**
- Use `go mod tidy -compat=1.22` to stay compatible with the declared minimum.
- Renovate/Dependabot on a weekly cadence; manual bump for `fiber/v2` (still actively patched for security).
- Do **not** auto-bump `geoip2-golang` past v1 — v2 renames struct fields and changes coord pointers.

---

## 2. Folder Layout

```
redirect-svc/
├── cmd/
│   └── redirect/
│       └── main.go               # wire-up only; no logic
├── internal/
│   ├── config/
│   │   └── config.go             # env parsing, validation
│   ├── handler/
│   │   ├── redirect.go           # GET /:code
│   │   └── health.go             # GET /health, /ready
│   ├── cache/
│   │   └── redis.go              # cache-aside Get/Set
│   ├── store/
│   │   └── postgres.go           # pgxpool + prepared statements
│   ├── events/
│   │   └── publisher.go          # Redis Streams XADD w/ bounded queue
│   ├── metrics/
│   │   └── metrics.go            # prometheus collectors
│   ├── middleware/
│   │   ├── requestid.go
│   │   └── geoip.go              # MaxMind lookup -> fiber.Locals
│   └── geoip/
│       └── reader.go             # thin wrapper over geoip2.Reader
├── deploy/
│   ├── Dockerfile
│   └── docker-compose.yml
├── test/
│   └── integration/              # testcontainers-go suites
├── go.mod
├── go.sum
└── Makefile
```

**Rules:**
- `cmd/` holds only `main.go` — assemble dependencies, call `app.Listen`.
- Nothing under `internal/` imports Fiber except `handler/` and `middleware/`.
- `store/`, `cache/`, `events/` expose narrow interfaces; handlers depend on interfaces, not structs.

---

## 3. Redis Cache-Aside (GET → SET on miss from PG)

Key format: `sc:<shortcode>` → JSON `{long_url, owner_id, expires_at}`.
TTL: **24h** for found, **5min negative cache** for not-found (prevents DB hammer on bad bots).

```go
// internal/cache/redis.go
package cache

import (
    "context"
    "encoding/json"
    "errors"
    "time"

    "github.com/redis/go-redis/v9"
)

const (
    keyPrefix     = "sc:"
    ttlHit        = 24 * time.Hour
    ttlNegative   = 5 * time.Minute
    sentinelMiss  = "__MISS__"
)

var ErrNotFound = errors.New("shortcode not found")

type Entry struct {
    LongURL   string    `json:"u"`
    OwnerID   string    `json:"o"`
    ExpiresAt time.Time `json:"e,omitempty"`
}

type Cache struct{ rdb *redis.Client }

func New(rdb *redis.Client) *Cache { return &Cache{rdb: rdb} }

// Get returns (entry, nil) on hit, (nil, ErrNotFound) on negative cache hit,
// (nil, redis.Nil) on true miss (caller should hit DB).
func (c *Cache) Get(ctx context.Context, code string) (*Entry, error) {
    raw, err := c.rdb.Get(ctx, keyPrefix+code).Result()
    if err != nil {
        return nil, err // redis.Nil bubbles up → caller fetches from PG
    }
    if raw == sentinelMiss {
        return nil, ErrNotFound
    }
    var e Entry
    if err := json.Unmarshal([]byte(raw), &e); err != nil {
        return nil, err
    }
    return &e, nil
}

func (c *Cache) SetHit(ctx context.Context, code string, e *Entry) error {
    b, err := json.Marshal(e)
    if err != nil {
        return err
    }
    return c.rdb.Set(ctx, keyPrefix+code, b, ttlHit).Err()
}

func (c *Cache) SetMiss(ctx context.Context, code string) error {
    return c.rdb.Set(ctx, keyPrefix+code, sentinelMiss, ttlNegative).Err()
}
```

Handler flow:

```go
func (h *RedirectHandler) Handle(c *fiber.Ctx) error {
    code := c.Params("code")
    ctx := c.UserContext()

    e, err := h.cache.Get(ctx, code)
    switch {
    case err == nil:
        metrics.CacheHits.Inc()
    case errors.Is(err, cache.ErrNotFound):
        metrics.CacheNegHits.Inc()
        return c.SendStatus(fiber.StatusNotFound)
    case errors.Is(err, redis.Nil):
        metrics.CacheMisses.Inc()
        e, err = h.store.FindByCode(ctx, code)
        if errors.Is(err, store.ErrNotFound) {
            _ = h.cache.SetMiss(ctx, code)
            return c.SendStatus(fiber.StatusNotFound)
        }
        if err != nil {
            metrics.Errors.WithLabelValues("db").Inc()
            return fiber.ErrServiceUnavailable
        }
        _ = h.cache.SetHit(ctx, code, e) // best-effort
    default:
        metrics.Errors.WithLabelValues("cache").Inc()
        // Fail-open: go to DB if Redis is down
        e, err = h.store.FindByCode(ctx, code)
        if err != nil { return fiber.ErrServiceUnavailable }
    }

    h.publisher.Publish(code, c) // non-blocking fire-and-forget
    return c.Redirect(e.LongURL, fiber.StatusFound)
}
```

**Use a Redis connection pool:** `redis.NewClient(&redis.Options{PoolSize: 100, MinIdleConns: 10, ReadTimeout: 200*time.Millisecond})`. Tight read timeout is critical — redirect latency budget is ~10ms p99.

---

## 4. Redis Streams Publisher (non-blocking)

Publishes click events to `stream:clicks` for downstream analytics (ClickHouse consumer). Never blocks the request path.

```go
// internal/events/publisher.go
package events

import (
    "context"
    "time"

    "github.com/gofiber/fiber/v2"
    "github.com/redis/go-redis/v9"
    "github.com/rs/zerolog"
)

type ClickEvent struct {
    Code       string
    IP         string
    UserAgent  string
    Referer    string
    Country    string
    City       string
    Timestamp  time.Time
}

type Publisher struct {
    rdb      *redis.Client
    stream   string
    maxLen   int64
    queue    chan ClickEvent
    log      zerolog.Logger
}

func New(rdb *redis.Client, stream string, log zerolog.Logger) *Publisher {
    p := &Publisher{
        rdb:    rdb,
        stream: stream,
        maxLen: 1_000_000,          // trim approx
        queue:  make(chan ClickEvent, 10_000), // bounded — drop on full
        log:    log,
    }
    for i := 0; i < 4; i++ { // worker pool
        go p.run()
    }
    return p
}

func (p *Publisher) Publish(code string, c *fiber.Ctx) {
    ev := ClickEvent{
        Code:      code,
        IP:        c.IP(),
        UserAgent: string(c.Request().Header.UserAgent()),
        Referer:   string(c.Request().Header.Referer()),
        Country:   c.Locals("geo_country").(string), // set by middleware
        City:      c.Locals("geo_city").(string),
        Timestamp: time.Now().UTC(),
    }
    select {
    case p.queue <- ev:
    default:
        // Queue full — drop. Metrics only; never block the redirect.
        metrics.EventsDropped.Inc()
    }
}

func (p *Publisher) run() {
    for ev := range p.queue {
        ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
        _, err := p.rdb.XAdd(ctx, &redis.XAddArgs{
            Stream: p.stream,
            MaxLen: p.maxLen,
            Approx: true, // ~ trimming is O(1) amortized
            Values: map[string]any{
                "code":  ev.Code,
                "ip":    ev.IP,
                "ua":    ev.UserAgent,
                "ref":   ev.Referer,
                "cc":    ev.Country,
                "city":  ev.City,
                "ts":    ev.Timestamp.UnixMilli(),
            },
        }).Result()
        cancel()
        if err != nil {
            p.log.Warn().Err(err).Msg("xadd failed")
            metrics.EventsFailed.Inc()
        }
    }
}

func (p *Publisher) Close() { close(p.queue) } // drain on shutdown
```

Key points: bounded channel (`10_000`), approx MAXLEN trim, separate timeout per XADD so a Redis hiccup doesn't stall workers, worker pool (4) to absorb bursts.

---

## 5. Postgres Fallback with pgx Pool

```go
// internal/store/postgres.go
package store

import (
    "context"
    "errors"
    "time"

    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("not found")

type Store struct{ pool *pgxpool.Pool }

func New(ctx context.Context, dsn string) (*Store, error) {
    cfg, err := pgxpool.ParseConfig(dsn)
    if err != nil { return nil, err }

    cfg.MinConns             = 5
    cfg.MaxConns             = 25
    cfg.MaxConnLifetime      = time.Hour
    cfg.MaxConnLifetimeJitter = 5 * time.Minute // avoid thundering reconnect
    cfg.MaxConnIdleTime      = 15 * time.Minute
    cfg.HealthCheckPeriod    = time.Minute
    cfg.ConnConfig.ConnectTimeout = 3 * time.Second

    // Pre-parse + use simple protocol for low-overhead single-param lookups
    cfg.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeCacheDescribe

    pool, err := pgxpool.NewWithConfig(ctx, cfg)
    if err != nil { return nil, err }
    if err := pool.Ping(ctx); err != nil { pool.Close(); return nil, err }
    return &Store{pool: pool}, nil
}

func (s *Store) FindByCode(ctx context.Context, code string) (*cache.Entry, error) {
    const q = `SELECT long_url, owner_id, COALESCE(expires_at, 'epoch'::timestamptz)
               FROM short_links WHERE code = $1 AND disabled = false`
    var e cache.Entry
    err := s.pool.QueryRow(ctx, q, code).Scan(&e.LongURL, &e.OwnerID, &e.ExpiresAt)
    if errors.Is(err, pgx.ErrNoRows) { return nil, ErrNotFound }
    return &e, err
}

func (s *Store) Ping(ctx context.Context) error { return s.pool.Ping(ctx) }
func (s *Store) Close()                         { s.pool.Close() }
```

**Sizing guidance** (redirect service only, read-path):
- `MinConns=5`, `MaxConns=25` per pod. Multiply by pod count; keep total under PG `max_connections - 20%`.
- If running 10 pods, cap at 25 each → 250 conns → needs PG tuned for ~400 `max_connections`, else use PgBouncer in transaction mode in front.

---

## 6. Fiber Middleware Chain

Order matters. Recover must be first; limiter last (so we log/instrument rejected requests too).

```go
// cmd/redirect/main.go (excerpt)
app := fiber.New(fiber.Config{
    ServerHeader:          "redirect",
    DisableStartupMessage: true,
    ReadTimeout:           5 * time.Second,  // MUST be >0 for graceful shutdown
    WriteTimeout:          5 * time.Second,
    IdleTimeout:           30 * time.Second,
    Prefork:               false,            // keep false — breaks metrics + shutdown
    AppName:               "redirect/1.0",
    ErrorHandler:          customErrorHandler,
})

app.Use(recover.New(recover.Config{EnableStackTrace: true}))
app.Use(requestid.New())
app.Use(fiberzerolog.New(fiberzerolog.Config{
    Logger: &log.Logger,
    Fields: []string{"latency", "status", "method", "url", "ip"},
}))

// Prometheus — mount BEFORE limiter so rejects are measured
prom := fiberprometheus.New("redirect")
prom.RegisterAt(app, "/metrics")
app.Use(prom.Middleware)

// GeoIP lookup middleware (reads once from in-memory mmdb)
app.Use(geomw.New(geoReader))

// Rate limit — per-IP, 1000 req/s burst, fail-open if storage is down
app.Use(limiter.New(limiter.Config{
    Max:               1000,
    Expiration:        1 * time.Second,
    LimiterMiddleware: limiter.SlidingWindow{},
    KeyGenerator:      func(c *fiber.Ctx) string { return c.IP() },
    SkipFailedRequests: true,
}))

app.Get("/health", healthHandler.Live)
app.Get("/ready",  healthHandler.Ready)
app.Get("/:code",  redirectHandler.Handle)
```

---

## 7. Graceful Shutdown

```go
// cmd/redirect/main.go (continued)
go func() {
    if err := app.Listen(":" + cfg.Port); err != nil && !errors.Is(err, http.ErrServerClosed) {
        log.Fatal().Err(err).Msg("listen failed")
    }
}()

sigCh := make(chan os.Signal, 1)
signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
<-sigCh
log.Info().Msg("shutdown signal received")

// Fiber: drain in-flight within timeout
shutdownCtx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
defer cancel()

if err := app.ShutdownWithContext(shutdownCtx); err != nil {
    log.Error().Err(err).Msg("fiber shutdown")
}

// Drain publisher queue (stop accepting, let goroutines flush)
publisher.Close()

// Close downstream pools
redisClient.Close()
streamClient.Close()
store.Close()
geoReader.Close()

log.Info().Msg("shutdown complete")
```

**Caveat:** Fiber v2 cancels in-flight request contexts the moment `Shutdown()` is called (known issue #3431). If you have slow handlers, wrap their context with `context.WithoutCancel` inside the handler, or copy needed values out before awaiting. For a pure redirect service this is a non-issue — handlers are sub-10ms.

---

## 8. Multistage Dockerfile → scratch

```dockerfile
# syntax=docker/dockerfile:1.7
ARG GO_VERSION=1.22

FROM golang:${GO_VERSION}-alpine AS build
RUN apk add --no-cache ca-certificates tzdata git
WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY . .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags='-s -w -buildid=' \
    -o /out/redirect ./cmd/redirect

# --- final stage: scratch, ~15MB ---
FROM scratch
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /usr/share/zoneinfo                /usr/share/zoneinfo
COPY --from=build /out/redirect                      /redirect

# GeoIP DB mounted as volume at runtime, not baked into image
VOLUME ["/geoip"]
ENV GEOIP_DB_PATH=/geoip/GeoLite2-City.mmdb

EXPOSE 8080
USER 65532:65532
ENTRYPOINT ["/redirect"]
```

Run: `docker run -v /srv/geoip:/geoip:ro -e REDIS_CACHE_URL=... redirect`.
Final image is ~15MB (binary + CA certs + tzdata).

---

## 9. Environment Variables (12-factor)

All config via env. Parse with `caarlos0/env/v11`.

| Variable             | Default                   | Notes                                    |
|----------------------|---------------------------|------------------------------------------|
| `PORT`               | `8080`                    | Listener port                            |
| `LOG_LEVEL`          | `info`                    | `trace`/`debug`/`info`/`warn`/`error`    |
| `LOG_FORMAT`         | `json`                    | `json` or `console`                      |
| `REDIS_CACHE_URL`    | (required)                | `redis://:pw@host:6379/0`                |
| `REDIS_STREAM_URL`   | (required)                | Separate instance/DB recommended         |
| `REDIS_POOL_SIZE`    | `100`                     |                                          |
| `PG_DSN`             | (required)                | `postgres://u:p@host:5432/db?sslmode=require` |
| `PG_MAX_CONNS`       | `25`                      |                                          |
| `PG_MIN_CONNS`       | `5`                       |                                          |
| `GEOIP_DB_PATH`      | `/geoip/GeoLite2-City.mmdb` |                                        |
| `SHUTDOWN_TIMEOUT`   | `20s`                     |                                          |
| `RATE_LIMIT_PER_SEC` | `1000`                    | Per-IP sliding window                    |
| `CACHE_TTL_HIT`      | `24h`                     |                                          |
| `CACHE_TTL_MISS`     | `5m`                      | Negative cache                           |
| `STREAM_NAME`        | `stream:clicks`           |                                          |
| `STREAM_MAXLEN`      | `1000000`                 | Approx trim                              |

```go
// internal/config/config.go
type Config struct {
    Port            string        `env:"PORT"             envDefault:"8080"`
    LogLevel        string        `env:"LOG_LEVEL"        envDefault:"info"`
    RedisCacheURL   string        `env:"REDIS_CACHE_URL,required"`
    RedisStreamURL  string        `env:"REDIS_STREAM_URL,required"`
    RedisPoolSize   int           `env:"REDIS_POOL_SIZE"  envDefault:"100"`
    PGDSN           string        `env:"PG_DSN,required"`
    PGMaxConns      int32         `env:"PG_MAX_CONNS"     envDefault:"25"`
    PGMinConns      int32         `env:"PG_MIN_CONNS"     envDefault:"5"`
    GeoIPDBPath     string        `env:"GEOIP_DB_PATH"    envDefault:"/geoip/GeoLite2-City.mmdb"`
    ShutdownTimeout time.Duration `env:"SHUTDOWN_TIMEOUT" envDefault:"20s"`
    StreamName      string        `env:"STREAM_NAME"      envDefault:"stream:clicks"`
    StreamMaxLen    int64         `env:"STREAM_MAXLEN"    envDefault:"1000000"`
}
```

---

## 10. Prometheus Metrics

```go
// internal/metrics/metrics.go
package metrics

import "github.com/prometheus/client_golang/prometheus"

var (
    RedirectLatency = prometheus.NewHistogramVec(prometheus.HistogramOpts{
        Name:    "redirect_request_duration_seconds",
        Help:    "End-to-end redirect handler latency.",
        // tight buckets — redirect budget is <10ms
        Buckets: []float64{.0005, .001, .002, .005, .01, .025, .05, .1, .25},
    }, []string{"status"})

    CacheHits    = prometheus.NewCounter(prometheus.CounterOpts{Name: "cache_hits_total"})
    CacheMisses  = prometheus.NewCounter(prometheus.CounterOpts{Name: "cache_misses_total"})
    CacheNegHits = prometheus.NewCounter(prometheus.CounterOpts{Name: "cache_negative_hits_total"})

    Errors = prometheus.NewCounterVec(prometheus.CounterOpts{
        Name: "redirect_errors_total",
    }, []string{"source"}) // "cache" | "db" | "stream" | "geoip"

    EventsDropped = prometheus.NewCounter(prometheus.CounterOpts{
        Name: "stream_events_dropped_total",
        Help: "Click events dropped due to full publisher queue.",
    })
    EventsFailed = prometheus.NewCounter(prometheus.CounterOpts{
        Name: "stream_events_failed_total",
        Help: "XADD errors.",
    })

    QueueDepth = prometheus.NewGaugeFunc(prometheus.GaugeOpts{
        Name: "stream_queue_depth",
    }, func() float64 { return float64(publisher.QueueLen()) })
)

func MustRegister(r prometheus.Registerer) {
    r.MustRegister(RedirectLatency, CacheHits, CacheMisses, CacheNegHits,
        Errors, EventsDropped, EventsFailed, QueueDepth)
}
```

**Alerts to define (in Prometheus rules):**
- `cache_hit_ratio < 0.9 for 5m` → warn (something is poisoning cache)
- `redirect_request_duration_seconds{quantile="0.99"} > 0.02` → warn
- `rate(stream_events_dropped_total[1m]) > 0` → critical
- `rate(redirect_errors_total{source="db"}[1m]) > 10` → critical

---

## 11. Healthcheck Endpoints

Split liveness vs readiness — k8s convention.

```go
// internal/handler/health.go
type Health struct {
    cache  *redis.Client
    stream *redis.Client
    store  *store.Store
    geo    *geoip.Reader
}

// Live: process is alive. Used by k8s livenessProbe. Never touches deps.
func (h *Health) Live(c *fiber.Ctx) error {
    return c.JSON(fiber.Map{"status": "ok"})
}

// Ready: can serve traffic. Used by k8s readinessProbe + LB.
func (h *Health) Ready(c *fiber.Ctx) error {
    ctx, cancel := context.WithTimeout(c.UserContext(), 2*time.Second)
    defer cancel()

    checks := map[string]string{
        "redis_cache":  pingRedis(ctx, h.cache),
        "redis_stream": pingRedis(ctx, h.stream),
        "postgres":     pingPG(ctx, h.store),
        "geoip":        pingGeo(h.geo),
    }
    ok := true
    for _, v := range checks { if v != "ok" { ok = false; break } }
    status := fiber.StatusOK
    if !ok { status = fiber.StatusServiceUnavailable }
    return c.Status(status).JSON(fiber.Map{"status": ok, "checks": checks})
}

func pingRedis(ctx context.Context, r *redis.Client) string {
    if err := r.Ping(ctx).Err(); err != nil { return err.Error() }
    return "ok"
}
func pingPG(ctx context.Context, s *store.Store) string {
    if err := s.Ping(ctx); err != nil { return err.Error() }
    return "ok"
}
func pingGeo(r *geoip.Reader) string {
    if r == nil { return "not loaded" }
    return "ok"
}
```

K8s probes:

```yaml
livenessProbe:
  httpGet: { path: /health, port: 8080 }
  periodSeconds: 10
  failureThreshold: 3
readinessProbe:
  httpGet: { path: /ready, port: 8080 }
  periodSeconds: 5
  failureThreshold: 2
  initialDelaySeconds: 3
```

---

## 12. Testing Approach (testcontainers-go)

Unit tests: mock the `Cache`, `Store`, `Publisher` interfaces. Keep handler tests pure.

Integration: spin up real Postgres + Redis containers per suite (not per test — too slow).

```go
// test/integration/redirect_test.go
package integration

import (
    "context"
    "testing"

    "github.com/testcontainers/testcontainers-go/modules/postgres"
    "github.com/testcontainers/testcontainers-go/modules/redis"
    "github.com/stretchr/testify/require"
)

var (
    pgCtr    *postgres.PostgresContainer
    redisCtr *redis.RedisContainer
)

func TestMain(m *testing.M) {
    ctx := context.Background()
    var err error
    pgCtr, err = postgres.Run(ctx, "postgres:16-alpine",
        postgres.WithDatabase("shorty"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
        postgres.BasicWaitStrategies(),
    )
    if err != nil { panic(err) }
    redisCtr, err = redis.Run(ctx, "redis:7-alpine")
    if err != nil { panic(err) }

    // seed schema + fixtures
    seed(ctx, pgCtr)

    code := m.Run()
    _ = pgCtr.Terminate(ctx)
    _ = redisCtr.Terminate(ctx)
    os.Exit(code)
}

func TestRedirect_CacheMissThenHit(t *testing.T) {
    app := buildApp(t, pgCtr, redisCtr)
    // first call — DB hit, cache populated
    resp1 := doReq(t, app, "/abc123")
    require.Equal(t, 302, resp1.StatusCode)
    // second call — cache hit (assert via metrics)
    resp2 := doReq(t, app, "/abc123")
    require.Equal(t, 302, resp2.StatusCode)
    require.Equal(t, "https://example.com/target", resp2.Header.Get("Location"))
}
```

Guidance:
- Use `t.Parallel()` inside tests, but share containers via `TestMain`.
- Use `ryuk` reaper (default) so stray containers are cleaned even on panic.
- Run integration suite in CI only; tag with `//go:build integration`.
- For XADD/consumer tests, use `redis.Run` with streams module — default image is fine.

---

## Gotchas (production pitfalls)

1. **Prefork breaks everything.** Fiber's `Prefork: true` breaks Prometheus (per-process registries), graceful shutdown, and keep-alive accounting. Leave it `false` — horizontal scale via more pods, not forks.

2. **`ReadTimeout: 0` + `ShutdownWithContext` = hang forever.** Fiber docs: keepalive connections aren't closed on shutdown if `ReadTimeout` is zero. Always set a non-zero `ReadTimeout`.

3. **In-flight context cancellation on shutdown.** Fiber v2 cancels `c.UserContext()` the moment `Shutdown()` runs. If you call Redis/PG from a shutting-down handler, calls will fail. For long operations, use `context.WithoutCancel(parent)` inside the handler.

4. **pgx `MinConns` lies.** The pool can dip below MinConns between health checks. If you need guaranteed warm conns for p99, prefer `MinIdleConns` (v5.5+) — but note it's still best-effort.

5. **Redis pool starvation under burst.** Default `PoolSize=10*GOMAXPROCS` is low for a redirect service. Set `PoolSize=100+`, `MinIdleConns=10`, and always set `ReadTimeout` — otherwise a single slow Redis call blocks a pool slot indefinitely.

6. **Stream MAXLEN without `Approx: true` is O(N).** Always pass `Approx: true` (the `~` flag). Exact trimming on every XADD at high QPS will destroy Redis latency.

7. **Negative caching is not optional.** Without it, a bot scanning `/aaaa`, `/aaab`, ... hits Postgres on every request. Cache "not found" for 5min minimum.

8. **`geoip2-golang` v2 is not a drop-in.** v2 rewrites struct fields (Title Case, pointer coords) and removes several helpers. Staying on v1.x until a coordinated migration is cheaper.

9. **MaxMind `.mmdb` in scratch image.** Don't bake it — the file is licensed and updates weekly. Mount as a read-only volume, refresh via sidecar/CronJob.

10. **CA certs in scratch.** Forgetting to copy `/etc/ssl/certs/ca-certificates.crt` means TLS (e.g., to a managed Redis) fails silently with `x509: certificate signed by unknown authority`.

11. **`CGO_ENABLED=0` is required for scratch.** Otherwise you pull glibc and scratch will crash. Also set `GOOS=linux` explicitly (matters when building from macOS/Windows dev machines).

12. **Fiber `c.IP()` trusts `X-Forwarded-For` only if configured.** Set `app.Config.ProxyHeader = "X-Forwarded-For"` AND `EnableTrustedProxyCheck: true` with your LB's CIDR, otherwise attackers can spoof IPs → skew rate limiter + geoip.

13. **Dropped events are silent by default.** Export `stream_events_dropped_total` and alert on it. A full queue usually means Redis Streams is overloaded, not that the service is healthy.

14. **Separate Redis instances for cache vs streams.** Cache is eviction-friendly (`allkeys-lru`), streams need `noeviction`. Same instance with `allkeys-lru` WILL silently drop stream entries under memory pressure.

15. **`zerolog` global logger in tests.** `log.Logger` is package-global; parallel tests stomp on each other's output. Inject `zerolog.Logger` explicitly into each component.

16. **Prometheus histogram cardinality.** Do NOT label by shortcode — unbounded. Label only by `status` (2xx/3xx/4xx/5xx bucket) or fixed sets.

---

## Appendix: One-line commands

```bash
# local dev
go run ./cmd/redirect

# build scratch image
docker build -f deploy/Dockerfile -t redirect:dev .

# integration tests
go test -tags=integration ./test/integration/...

# benchmark redirect handler
go test -run=^$ -bench=BenchmarkRedirect -benchmem ./internal/handler

# load test (vegeta)
echo "GET http://localhost:8080/abc123" | vegeta attack -rate=5000 -duration=30s | vegeta report
```
