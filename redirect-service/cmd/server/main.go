// Command redirect-service is the hot-path HTTP redirector:
//
//	GET /{code}  → 302 / 404 / 410 / 451
//	GET /health  → JSON liveness+readiness
//	GET /metrics → Prometheus exposition
//
// Target p99: <5ms (cache hit).
package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/ansrivas/fiberprometheus/v2"
	"github.com/gofiber/contrib/fiberzerolog"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/adaptor"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/urlshortener/redirect-service/internal/cache"
	"github.com/urlshortener/redirect-service/internal/config"
	"github.com/urlshortener/redirect-service/internal/events"
	"github.com/urlshortener/redirect-service/internal/geoip"
	"github.com/urlshortener/redirect-service/internal/handler"
	"github.com/urlshortener/redirect-service/internal/metrics"
	"github.com/urlshortener/redirect-service/internal/middleware"
	"github.com/urlshortener/redirect-service/internal/store"
)

func main() {
	// Sub-command: `redirect healthcheck` — used by Docker HEALTHCHECK since
	// distroless/static has no wget/curl/shell.
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(runHealthcheck())
	}

	if err := run(); err != nil {
		log.Fatal().Err(err).Msg("fatal")
	}
}

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	logger := initLogger(cfg.LogLevel, cfg.LogFormat)
	log.Logger = logger

	logger.Info().
		Str("http_port", cfg.HTTPPort).
		Str("redis_cache", redactURL(cfg.RedisCacheURL)).
		Str("redis_stream", redactURL(cfg.RedisStreamURL)).
		Str("pg_dsn", redactURL(cfg.PGDSN)).
		Msg("starting redirect-service")

	// Root context cancels on SIGINT/SIGTERM.
	rootCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// --- dependencies -----------------------------------------------------

	// Postgres
	pgCtx, pgCancel := context.WithTimeout(rootCtx, 5*time.Second)
	pgStore, err := store.New(pgCtx, cfg.PGDSN, cfg.PGMinConns, cfg.PGMaxConns, cfg.PGQueryTimeout)
	pgCancel()
	if err != nil {
		return fmt.Errorf("postgres: %w", err)
	}
	defer pgStore.Close()

	// Redis — two clients (contract section 4).
	cacheRedis, err := newRedisClient(cfg.RedisCacheURL, cfg)
	if err != nil {
		return fmt.Errorf("redis cache: %w", err)
	}
	defer func() { _ = cacheRedis.Close() }()

	streamRedis, err := newRedisClient(cfg.RedisStreamURL, cfg)
	if err != nil {
		return fmt.Errorf("redis stream: %w", err)
	}
	defer func() { _ = streamRedis.Close() }()

	pingCtx, pingCancel := context.WithTimeout(rootCtx, 3*time.Second)
	if err := cacheRedis.Ping(pingCtx).Err(); err != nil {
		logger.Warn().Err(err).Msg("redis-cache ping failed at startup")
	}
	if err := streamRedis.Ping(pingCtx).Err(); err != nil {
		logger.Warn().Err(err).Msg("redis-app ping failed at startup")
	}
	pingCancel()

	cch := cache.New(cacheRedis, cfg.CacheTTLHit, cfg.CacheTTLMiss)

	// GeoIP — tolerate missing .mmdb (contract/HLA: degrade to "XX").
	geoReader, err := geoip.Open(cfg.GeoIPDBPath)
	if err != nil {
		logger.Warn().Err(err).Str("path", cfg.GeoIPDBPath).Msg("geoip open failed; using noop")
		geoReader = geoip.NoopReader{}
	}
	if !geoReader.Loaded() {
		logger.Warn().Str("path", cfg.GeoIPDBPath).Msg("geoip .mmdb not loaded; lookups will return XX")
	}
	defer func() { _ = geoReader.Close() }()

	// Click event publisher.
	publisher := events.New(streamRedis, events.Config{
		Stream:  cfg.StreamName,
		MaxLen:  cfg.StreamMaxLen,
		Workers: cfg.StreamWorkers,
		Buffer:  cfg.StreamBuffer,
	}, logger.With().Str("component", "publisher").Logger())
	publisher.Start(rootCtx)

	// --- fiber ------------------------------------------------------------

	app := fiber.New(fiber.Config{
		ServerHeader:            "redirect",
		AppName:                 "redirect/1.0",
		DisableStartupMessage:   true,
		ReadTimeout:             5 * time.Second,
		WriteTimeout:            5 * time.Second,
		IdleTimeout:             30 * time.Second,
		Prefork:                 false,
		ProxyHeader:             proxyHeader(cfg),
		EnableTrustedProxyCheck: cfg.TrustProxy,
		TrustedProxies:          defaultTrustedProxies(),
	})

	app.Use(recover.New(recover.Config{EnableStackTrace: true}))
	app.Use(middleware.RequestID())
	app.Use(fiberzerolog.New(fiberzerolog.Config{
		Logger: &logger,
		Fields: []string{"latency", "status", "method", "url", "ip", "ua", "requestId"},
	}))

	// Prometheus: fiberprometheus registers its own HTTP-level metrics
	// into our custom Registry so we can serve everything from a single
	// /metrics endpoint (our custom counters + its http histograms).
	fiberProm := fiberprometheus.NewWithRegistry(metrics.Registry, "redirect_service", "http", "", nil)
	fiberProm.RegisterAt(app, "/metrics")
	app.Use(fiberProm.Middleware)

	// Fallback: serve our Registry directly (useful if fiberprometheus version
	// handling changes). Same data, alternate path.
	app.Get("/metrics/app", adaptor.HTTPHandler(promhttp.HandlerFor(metrics.Registry, promhttp.HandlerOpts{})))

	app.Get("/health", handler.Health(handler.HealthDeps{
		Cache: cch,
		StreamPing: func(ctx context.Context) error {
			return streamRedis.Ping(ctx).Err()
		},
		Store: pgStore,
		GeoIP: geoReader,
	}))

	app.Get("/:code", handler.Redirect(handler.RedirectDeps{
		Cache:               cch,
		Store:               pgStore,
		Publisher:           publisher,
		GeoIP:               geoReader,
		Log:                 logger,
		RoutingEnabled:      cfg.RoutingEnabled,
		InterstitialDelayMS: cfg.PixelInterstitialDelay,
	}))

	// --- serve + graceful shutdown ---------------------------------------

	errCh := make(chan error, 1)
	go func() {
		addr := ":" + cfg.HTTPPort
		logger.Info().Str("addr", addr).Msg("http listen")
		if err := app.Listen(addr); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()

	select {
	case <-rootCtx.Done():
		logger.Info().Msg("shutdown signal received")
	case err := <-errCh:
		logger.Error().Err(err).Msg("listen failed")
		return err
	}

	return gracefulShutdown(app, publisher, cfg.ShutdownTimeout, logger)
}

func gracefulShutdown(app *fiber.App, publisher *events.Publisher, timeout time.Duration, logger zerolog.Logger) error {
	shutdownCtx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	if err := app.ShutdownWithContext(shutdownCtx); err != nil {
		logger.Warn().Err(err).Msg("fiber shutdown")
	}

	// Drain publisher with the remaining budget.
	deadline, ok := shutdownCtx.Deadline()
	budget := 5 * time.Second
	if ok {
		if d := time.Until(deadline); d > 0 {
			budget = d
		}
	}
	if err := publisher.Close(budget); err != nil {
		logger.Warn().Err(err).Msg("publisher close timed out")
	}

	logger.Info().Msg("shutdown complete")
	return nil
}

// --- helpers --------------------------------------------------------------

func newRedisClient(rawURL string, cfg *config.Config) (*redis.Client, error) {
	opts, err := redis.ParseURL(rawURL)
	if err != nil {
		return nil, err
	}
	opts.PoolSize = cfg.RedisPoolSize
	opts.MinIdleConns = cfg.RedisMinIdleConns
	opts.ReadTimeout = cfg.RedisReadTimeout
	opts.WriteTimeout = cfg.RedisWriteTimeout
	opts.DialTimeout = 2 * time.Second
	return redis.NewClient(opts), nil
}

func initLogger(level, format string) zerolog.Logger {
	zerolog.TimeFieldFormat = time.RFC3339Nano
	lvl, err := zerolog.ParseLevel(strings.ToLower(level))
	if err != nil || lvl == zerolog.NoLevel {
		lvl = zerolog.InfoLevel
	}
	zerolog.SetGlobalLevel(lvl)

	var logger zerolog.Logger
	if strings.ToLower(format) == "console" {
		logger = zerolog.New(zerolog.ConsoleWriter{Out: os.Stderr, TimeFormat: time.RFC3339}).With().Timestamp().Logger()
	} else {
		logger = zerolog.New(os.Stdout).With().Timestamp().Str("service", "redirect").Logger()
	}
	return logger.Level(lvl)
}

func proxyHeader(cfg *config.Config) string {
	if !cfg.TrustProxy {
		return ""
	}
	if cfg.ProxyHeader == "" {
		return "X-Forwarded-For"
	}
	return cfg.ProxyHeader
}

// defaultTrustedProxies returns the internal Docker subnet (contract §1: 172.28.0.0/16)
// plus common private ranges so nginx on the same compose network is trusted.
func defaultTrustedProxies() []string {
	return []string{
		"127.0.0.1/32",
		"172.28.0.0/16",
		"10.0.0.0/8",
		"172.16.0.0/12",
		"192.168.0.0/16",
	}
}

// redactURL strips user:password from a URL for logging.
func redactURL(u string) string {
	if i := strings.Index(u, "@"); i > 0 {
		if j := strings.Index(u, "://"); j > 0 && j < i {
			return u[:j+3] + "***@" + u[i+1:]
		}
	}
	return u
}

// runHealthcheck is invoked by `redirect healthcheck` (docker HEALTHCHECK).
// Dials 127.0.0.1:$HTTP_PORT/health, expects HTTP 200.
func runHealthcheck() int {
	port := os.Getenv("HTTP_PORT")
	if port == "" {
		port = "8080"
	}
	// Intentional use of 127.0.0.1: this runs *inside* the container.
	url := fmt.Sprintf("http://127.0.0.1:%s/health", port)
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		fmt.Fprintln(os.Stderr, "healthcheck error:", err)
		return 1
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintln(os.Stderr, "healthcheck bad status:", resp.StatusCode)
		return 1
	}
	return 0
}
