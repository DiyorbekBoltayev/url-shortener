package handler

import (
	"context"
	"time"

	"github.com/gofiber/fiber/v2"

	"github.com/urlshortener/redirect-service/internal/cache"
	"github.com/urlshortener/redirect-service/internal/geoip"
	"github.com/urlshortener/redirect-service/internal/store"
)

// HealthDeps bundles dependencies checked by /health.
type HealthDeps struct {
	Cache       *cache.Cache
	StreamPing  func(ctx context.Context) error // redis-app ping
	Store       *store.Store
	GeoIP       geoip.Reader
	CheckBudget time.Duration // 0 → 2s default
}

// Health registers the /health endpoint per INTEGRATION_CONTRACT section 8:
//
//	{ "status": "ok", "checks": { "redis_cache": "ok", "redis_stream": "ok", "postgres": "ok" } }
//
// Returns 200 when all checks OK; 503 otherwise.
func Health(deps HealthDeps) fiber.Handler {
	budget := deps.CheckBudget
	if budget <= 0 {
		budget = 2 * time.Second
	}
	return func(c *fiber.Ctx) error {
		ctx, cancel := context.WithTimeout(c.UserContext(), budget)
		defer cancel()

		checks := map[string]string{
			"redis_cache":  stringifyErr(deps.Cache.Ping(ctx)),
			"redis_stream": stringifyErr(safePing(ctx, deps.StreamPing)),
			"postgres":     stringifyErr(deps.Store.Ping(ctx)),
		}
		if deps.GeoIP != nil && !deps.GeoIP.Loaded() {
			// Advisory — GeoIP missing is not fatal (HLA 2.1).
			checks["geoip"] = "degraded"
		} else if deps.GeoIP != nil {
			checks["geoip"] = "ok"
		}

		allOK := true
		for k, v := range checks {
			if k == "geoip" { // geoip is advisory
				continue
			}
			if v != "ok" {
				allOK = false
				break
			}
		}

		status := "ok"
		code := fiber.StatusOK
		if !allOK {
			status = "degraded"
			code = fiber.StatusServiceUnavailable
		}
		return c.Status(code).JSON(fiber.Map{
			"status": status,
			"checks": checks,
		})
	}
}

func stringifyErr(err error) string {
	if err == nil {
		return "ok"
	}
	return err.Error()
}

func safePing(ctx context.Context, fn func(context.Context) error) error {
	if fn == nil {
		return nil
	}
	return fn(ctx)
}
