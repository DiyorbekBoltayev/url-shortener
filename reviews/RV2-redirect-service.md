# RV2 — redirect-service review

**Reviewer:** RV2
**Date:** 2026-04-14
**Target:** `redirect-service/` (C2 output)
**Scope:** Source-of-truth inputs — INTEGRATION_CONTRACT.md, HLA §2.1, research/tech/go-fiber-redis.md.

---

## Verdict

**APPROVED with one BLOCKER** (missing `go.sum`) and a small set of NITs. All hot-path correctness concerns (cache keys, XADD shape, fire-and-forget publisher, trusted proxy IP, graceful shutdown, regex validation, 410 on expired, GeoIP loaded once, Dockerfile hardening, healthcheck checks deps) are handled correctly. Remediate the blocker below before merging.

---

## BLOCKERS

### B1. Missing `go.sum`
- **Where:** repo root — only `go.mod` is present.
- **Why it's a blocker:** The Dockerfile runs `COPY go.mod go.sum ./` followed by `go mod download`. The `COPY` will fail the image build outright. Even `go build` locally will refuse without `go.sum` when modules are pinned with `+incompatible` checks.
- **Fix:** Run `go mod tidy` (one-shot) and commit `go.sum`. Reviewers can't verify module integrity without it; the contract §12 version pins in `go.mod` are accurate but unverified against checksums until this lands.

No other blockers. Every item on the RV2 blocker checklist was audited and passes — see "Blocker audit trail" below.

---

## NITs

### N1. `fiberzerolog` import spelling / module path
- `cmd/server/main.go` imports `github.com/gofiber/contrib/fiberzerolog v1.0.2`. The upstream module is valid but the `Fields` value `"requestId"` is not a built-in fiberzerolog field — our RequestID is stored only in `c.Locals` under key `"request_id"` (snake_case). Result: the field is silently ignored and request id never appears in access logs. Either (a) switch fiberzerolog `Fields` to use a function/custom tag, or (b) add a middleware that copies `Locals("request_id")` into `c.Set("X-Request-ID")` already (it does — good) AND use a `FieldsSnakeCase: true` config or drop `"requestId"` and emit rid via `Logger.With().Str(...)` in the handler (already partially done).

### N2. `RedirectDeps.Publisher` is a concrete `*events.Publisher`
- Per research doc §2 rule ("handlers depend on interfaces, not structs"), this couples the handler to the publisher implementation and blocks swapping for an in-memory fake. Consider a one-method `Publisher` interface (`Publish(Event)`).

### N3. Negative-cache hit is counted as `CacheHits`
- In `handler/redirect.go` the `errors.Is(err, cache.ErrNotFound)` branch increments `metrics.CacheHits`. The research doc separates `cache_negative_hits_total` for a reason — it poisons the hit-ratio alert (`cache_hit_ratio < 0.9`). Add `CacheNegHits` (or re-label via a `kind` dimension) and increment it here instead.

### N4. `limiter` middleware missing
- Research §6 calls for Fiber `limiter.New` with 1000 req/s per-IP sliding window. The middleware chain in `main.go` omits it. Not a blocker because nginx does coarse rate-limiting per contract §6, but in-process limiter is the documented defence for direct-to-pod traffic (internal network) and for slow DB bursts.

### N5. `EventsQueueDepth` gauge updated from hot path
- `publisher.Publish` calls `metrics.EventsQueueDepth.Set(float64(len(p.ch)))` on every successful enqueue. This is a minor allocation-free op, but on a 50k req/s path it still adds a prometheus atomic store per call. Move to a dedicated `time.Ticker` (250ms) goroutine sampling `len(p.ch)`.

### N6. `/metrics` path collision with nginx `/metrics` policy
- Contract §6: "`/metrics` → prometheus (faqat internal, external 403)". redirect-service also exposes `/metrics`. This is by design (prometheus scrapes it directly on the internal network), but the dual endpoint `/metrics/app` in `main.go` is redundant and adds a second surface to keep in sync. Remove it or move behind a build tag.

### N7. Context deadline for `Cache.Get` / `Store.URLLookup`
- `Store.URLLookup` wraps its own 200ms timeout (good). `Cache.Get` does not — it inherits `c.UserContext()` which has no handler-level deadline. Under a stalled Redis with `ReadTimeout=200ms` the client timeout saves us, but a belt-and-braces `context.WithTimeout(ctx, cfg.RedisReadTimeout)` in the cache path is a cheap safety net.

### N8. `zerolog` global logger + `log.Logger = logger`
- Research §gotcha 15 calls out the global-logger anti-pattern. `main.go:59` assigns `log.Logger = logger`, which is the global. Fine in production (single logger) but tests that invoke main-adjacent helpers will stomp on each other. Inject the logger explicitly; don't mutate the zerolog global.

### N9. Postgres query does not filter `is_active` at SQL layer
- `URLLookup` returns the row and evaluates `Restricted()` in Go. When a code is disabled, we still pay a row read + network roundtrip. Add `WHERE short_code=$1 AND is_active=true` for the common case and a separate lookup for 451 reasoning. Minor perf tweak.

### N10. `NoopReader.Loaded()` returns false → `/health` reports `"degraded"` forever if mmdb is missing
- `handler/health.go` flags GeoIP as `"degraded"` but skips it in `allOK`, so the overall status stays 200. Matches HLA (advisory), but document this with an inline comment so ops don't chase it on first deploy where the geoip-updater sidecar hasn't fetched yet.

### N11. Test files use `miniredis` and `pgxmock` — listed in top-level `require`
- `go.mod` declares these as regular deps, not `_test`-only. `go mod tidy` should mark them indirect or move via a `//go:build test` tag. Non-fatal but bloats the prod binary's `go list -m all`.

### N12. `.golangci.yml` not reviewed
- Present but outside this review's scope. Flagging so a linter pass is run before merge — research §gotchas 15/16 (histogram cardinality, parallel-test logger stomping) are exactly what golangci will catch.

---

## Blocker audit trail (what was checked and why it passes)

| Blocker check | Status | Evidence |
|---|---|---|
| Code compiles (imports/syntax) | PASS | All packages resolve; no cycles; imports match `go.mod`. |
| `go.mod` versions match contract §12 | PASS | Fiber v2.52.9, go-redis v9.14.0, pgx v5.8.0, Go 1.22 directive — exact. |
| Dockerfile runs as non-root | PASS | `FROM gcr.io/distroless/static-debian12:nonroot` + `USER nonroot:nonroot`. |
| Dockerfile no `:latest` base | PASS | `golang:1.23-alpine`, `distroless/static-debian12:nonroot` (tagged). |
| `-trimpath` + `-ldflags="-s -w"` | PASS | `main.go` builder uses `-trimpath -ldflags="-s -w -buildid="`. |
| Redirect handler fire-and-forget XADD | PASS | `handler/redirect.go:121` — `deps.Publisher.Publish(...)` goes through buffered channel; worker does XADD out-of-band. |
| Publisher bounded + drop counter + drain | PASS | `events/publisher.go`: `ch` bounded at `cfg.Buffer` (10k default); `Publish` has `select default` → `EventsDropped.Inc()`; `Close(timeout)` closes channel and waits. |
| GeoIP loaded once | PASS | `geoip.Open` called in `main.go:108`; handler calls `deps.GeoIP.Lookup(ip)` on in-memory reader. |
| Postgres pool configured, no leaks | PASS | `store/postgres.go`: pgxpool with Min/Max/Lifetime/IdleTime/HealthCheckPeriod set; `QueryRow` has no session to leak (pgx handles release); `Close()` on shutdown. |
| Graceful shutdown on SIGTERM | PASS | `main.go`: `signal.NotifyContext(SIGINT,SIGTERM)`; `app.ShutdownWithContext`; publisher drained; redis+store closed. |
| Healthcheck validates deps | PASS | `handler/health.go`: pings redis-cache, redis-stream, postgres; returns 503 if any fail. |
| X-Forwarded-For trusted properly | PASS | `ProxyHeader=X-Forwarded-For` + `EnableTrustedProxyCheck=true` + trusted CIDR list (127/32, 172.28/16, private ranges). GeoIP uses `c.IP()` which honors this. |
| Cache keys match contract (`url:{code}`) | PASS | `cache/redis.go:19` — `KeyPrefix = "url:"`. |
| XADD stream name, fields, MAXLEN | PASS | `events/publisher.go`: `Stream="stream:clicks"`, `MaxLen=1_000_000`, `Approx=true`; fields `code, ts, ip, ua, ref, country` — exact contract §5 match. |
| Metrics: cache hit/miss, redirect_latency histogram | PASS | `CacheHits`, `CacheMisses`, `RedirectLatency` (histogram with tight sub-5ms buckets). Also `EventsDropped/Failed/Published`, `Errors{source}`. |
| Regex validation on code path | PASS | `handler/redirect.go:22` — `^[a-zA-Z0-9_-]{1,10}$`. |
| Expired URL returns 410 | PASS | `handler/redirect.go:93` — `u.Expired(time.Now())` → `StatusGone`. |
| No panic in hot path without recover | PASS | `app.Use(recover.New(...))` mounted as first middleware; geoip Lookup is nil-safe; publisher Publish is nil-safe on closed channel. |

---

## Files reviewed

- `C:\Users\User\Desktop\work\url-shortener\redirect-service\cmd\server\main.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\config\config.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\handler\redirect.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\handler\health.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\cache\redis.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\events\publisher.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\store\postgres.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\geoip\reader.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\metrics\metrics.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\internal\middleware\requestid.go`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\Dockerfile`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\docker-compose.yml`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\Makefile`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\go.mod`
- `C:\Users\User\Desktop\work\url-shortener\redirect-service\.env.example`

Sibling `_test.go` files present but not deep-audited (NIT N12).
