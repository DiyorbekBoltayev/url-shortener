// Package handler holds Fiber HTTP handlers for redirect-service.
package handler

import (
	"encoding/json"
	"errors"
	"regexp"
	"strconv"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"

	"github.com/urlshortener/redirect-service/internal/cache"
	"github.com/urlshortener/redirect-service/internal/events"
	"github.com/urlshortener/redirect-service/internal/geoip"
	"github.com/urlshortener/redirect-service/internal/metrics"
	"github.com/urlshortener/redirect-service/internal/middleware"
	"github.com/urlshortener/redirect-service/internal/routing"
	"github.com/urlshortener/redirect-service/internal/store"
)

// codeRegex enforces the 1-10 alnum (+ `_-`) short-code shape per HLA 2.1.
var codeRegex = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,10}$`)

// RedirectDeps bundles dependencies of the redirect handler.
type RedirectDeps struct {
	Cache     *cache.Cache
	Store     *store.Store
	Publisher *events.Publisher
	GeoIP     geoip.Reader
	Log       zerolog.Logger

	// RoutingEnabled is the feature flag for the S2 rule resolver +
	// pixel interstitial. When false the handler behaves exactly like the
	// pre-S2 version: single Redis GET, 302.
	RoutingEnabled bool

	// InterstitialDelayMS is the JS setTimeout delay before window.location.replace.
	// A small delay (150ms by default) lets pixel beacons fire before navigation.
	InterstitialDelayMS int
}

// Redirect returns the Fiber handler for GET /:code.
//
// Flow (HLA 2.1 + S2):
//  1. Validate code shape (fast regex).
//  2. Redis cache-aside lookup for the long URL.
//  3. On miss → Postgres fallback with a 200ms timeout; on found, set cache.
//  4. Apply expiry / restriction gates (410 / 451).
//  5. If rules_enabled: check `url:meta:{code}` for has_rules / has_pixels.
//     - has_rules  → fetch `url:rules:{code}`, run routing.Resolve to pick
//       a destination + branch label.
//     - has_pixels → fetch `url:pixels:{code}`, render HTML interstitial
//       instead of emitting 302.
//  6. Publish click event (non-blocking) with the branch label.
//  7. 302 Location: <destination>, or 200 HTML interstitial.
func Redirect(deps RedirectDeps) fiber.Handler {
	return func(c *fiber.Ctx) error {
		start := time.Now()
		code := c.Params("code")

		if !codeRegex.MatchString(code) {
			return finish(c, fiber.StatusNotFound, start)
		}

		ctx := c.UserContext()
		rid, _ := c.Locals(middleware.LocalsKeyRequestID).(string)
		logger := deps.Log.With().Str("code", code).Str("rid", rid).Logger()

		// 1. Cache
		longURL, err := deps.Cache.Get(ctx, code)
		switch {
		case err == nil:
			metrics.CacheHits.Inc()
			return servePositive(c, deps, code, longURL, start, logger)

		case errors.Is(err, cache.ErrNotFound):
			// Negative-cache hit — known missing.
			metrics.CacheHits.Inc()
			return finish(c, fiber.StatusNotFound, start)

		case errors.Is(err, cache.ErrCacheMiss):
			metrics.CacheMisses.Inc()
			// Fall through to PG.

		default:
			metrics.Errors.WithLabelValues("cache").Inc()
			logger.Warn().Err(err).Msg("cache get failed; falling back to PG")
			// Fail-open to Postgres.
		}

		// 2. Postgres fallback
		metrics.PGFallback.Inc()
		u, err := deps.Store.URLLookup(ctx, code)
		switch {
		case errors.Is(err, store.ErrNotFound):
			_ = deps.Cache.SetMiss(ctx, code) // best-effort
			return finish(c, fiber.StatusNotFound, start)

		case err != nil:
			metrics.Errors.WithLabelValues("db").Inc()
			logger.Error().Err(err).Msg("db lookup failed")
			return finish(c, fiber.StatusServiceUnavailable, start)
		}

		// 3. Gate: expired
		if u.Expired(time.Now()) {
			return finish(c, fiber.StatusGone, start)
		}

		// 4. Gate: inactive / password-protected
		if u.Restricted() {
			// Forward to api-service handler would go through nginx,
			// but at this layer we return 451 per HLA 2.1 / contract §7.
			return finish(c, fiber.StatusUnavailableForLegalReasons, start)
		}

		// 5. Populate cache (best-effort) then serve
		if setErr := deps.Cache.SetHit(ctx, code, u.LongURL); setErr != nil {
			metrics.Errors.WithLabelValues("cache").Inc()
			logger.Warn().Err(setErr).Msg("cache set failed")
		}
		return servePositive(c, deps, code, u.LongURL, start, logger)
	}
}

// servePositive is the path taken after we have a valid long URL. This is
// where the S2 rule resolver and pixel interstitial live — it is a no-op
// fast path when RoutingEnabled=false or when url:meta:{code} is absent.
func servePositive(c *fiber.Ctx, deps RedirectDeps, code, longURL string, start time.Time, logger zerolog.Logger) error {
	destination := longURL
	branch := routing.BranchDirect

	// GeoIP (in-memory, ~us). c.IP() already honors ProxyHeader when
	// EnableTrustedProxyCheck is set via fiber.Config.
	country := geoip.UnknownCountry
	if deps.GeoIP != nil {
		country = deps.GeoIP.Lookup(c.IP())
	}

	// Pixels are only fetched when meta says so. This keeps the no-pixel
	// path at a single Redis GET.
	var pixels []Pixel

	if deps.RoutingEnabled {
		ctx := c.UserContext()
		meta, err := deps.Cache.GetMeta(ctx, code)
		if err != nil {
			// Fail-open: any transport error degrades to the direct path.
			metrics.Errors.WithLabelValues("cache").Inc()
			logger.Warn().Err(err).Msg("cache meta fetch failed; serving direct")
		} else if meta != nil {
			ua := string(c.Request().Header.UserAgent())

			if meta.HasRules {
				rulesJSON, rErr := deps.Cache.GetRules(ctx, code)
				if rErr != nil {
					metrics.Errors.WithLabelValues("cache").Inc()
					logger.Warn().Err(rErr).Msg("cache rules fetch failed; serving direct")
				} else if rulesJSON != "" {
					var rules routing.RoutingRules
					if jErr := json.Unmarshal([]byte(rulesJSON), &rules); jErr != nil {
						metrics.Errors.WithLabelValues("handler").Inc()
						logger.Warn().Err(jErr).Msg("invalid routing rules json; serving direct")
					} else {
						destination, branch = routing.Resolve(&rules, country, ua, longURL)
					}
				}
			}

			if meta.HasPixels {
				pxJSON, pErr := deps.Cache.GetPixels(ctx, code)
				if pErr != nil {
					metrics.Errors.WithLabelValues("cache").Inc()
					logger.Warn().Err(pErr).Msg("cache pixels fetch failed; skipping interstitial")
				} else if pxJSON != "" {
					pixels = decodePixels(pxJSON)
				}
			}
		}
	}

	// Fire-and-forget publish.
	deps.Publisher.Publish(events.Event{
		Code:    code,
		TsMs:    time.Now().UnixMilli(),
		IP:      c.IP(),
		UA:      string(c.Request().Header.UserAgent()),
		Referer: string(c.Request().Header.Referer()),
		Country: country,
		Branch:  branch,
	})
	metrics.RouteBranch.WithLabelValues(branch).Inc()

	// If we have pixels, return the HTML interstitial. Otherwise plain 302.
	if len(pixels) > 0 {
		delay := deps.InterstitialDelayMS
		if delay <= 0 {
			delay = 150
		}
		body, err := renderInterstitial(destination, pixels, delay)
		if err != nil {
			metrics.Errors.WithLabelValues("handler").Inc()
			logger.Warn().Err(err).Msg("interstitial render failed; falling back to 302")
			// Fall through to plain 302.
		} else {
			metrics.InterstitialServed.Inc()
			c.Set(fiber.HeaderCacheControl, "no-store")
			c.Type("html")
			recordMetrics(fiber.StatusOK, start)
			return c.Status(fiber.StatusOK).Send(body)
		}
	}

	c.Set(fiber.HeaderCacheControl, "no-store")
	c.Set(fiber.HeaderLocation, destination)
	recordMetrics(fiber.StatusFound, start)
	return c.SendStatus(fiber.StatusFound)
}

// finish records metrics and sends `status` with an empty body. Used for
// non-302 terminal responses.
func finish(c *fiber.Ctx, status int, start time.Time) error {
	recordMetrics(status, start)
	return c.SendStatus(status)
}

func recordMetrics(status int, start time.Time) {
	label := strconv.Itoa(status)
	metrics.RedirectRequests.WithLabelValues(label).Inc()
	metrics.RedirectLatency.WithLabelValues(label).Observe(time.Since(start).Seconds())
}
