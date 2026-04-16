// Package config parses the service configuration from environment variables.
//
// All fields use the `env` tag convention so they can be loaded with
// github.com/caarlos0/env/v11. Defaults match INTEGRATION_CONTRACT.md.
package config

import (
	"fmt"
	"time"

	"github.com/caarlos0/env/v11"
)

// Config is the parsed service configuration.
type Config struct {
	// HTTP
	HTTPPort  string `env:"HTTP_PORT"   envDefault:"8080"`
	LogLevel  string `env:"LOG_LEVEL"   envDefault:"info"`
	LogFormat string `env:"LOG_FORMAT"  envDefault:"json"`

	// Redis — two instances per contract section 4.
	RedisCacheURL      string        `env:"REDIS_CACHE_URL,required"`
	RedisStreamURL     string        `env:"REDIS_STREAM_URL,required"`
	RedisPoolSize      int           `env:"REDIS_POOL_SIZE"        envDefault:"100"`
	RedisMinIdleConns  int           `env:"REDIS_MIN_IDLE_CONNS"   envDefault:"10"`
	RedisReadTimeout   time.Duration `env:"REDIS_READ_TIMEOUT_MS"  envDefault:"200ms"`
	RedisWriteTimeout  time.Duration `env:"REDIS_WRITE_TIMEOUT_MS" envDefault:"200ms"`

	// Postgres
	PGDSN            string        `env:"PG_DSN,required"`
	PGMaxConns       int32         `env:"PG_MAX_CONNS"          envDefault:"20"`
	PGMinConns       int32         `env:"PG_MIN_CONNS"          envDefault:"2"`
	PGQueryTimeout   time.Duration `env:"PG_QUERY_TIMEOUT_MS"   envDefault:"200ms"`

	// GeoIP
	GeoIPDBPath string `env:"GEOIP_DB_PATH" envDefault:"/data/GeoLite2-City.mmdb"`

	// Streams — contract section 5.
	StreamName    string `env:"STREAM_NAME"    envDefault:"stream:clicks"`
	StreamMaxLen  int64  `env:"STREAM_MAXLEN"  envDefault:"1000000"`
	StreamWorkers int    `env:"STREAM_WORKERS" envDefault:"4"`
	StreamBuffer  int    `env:"STREAM_BUFFER"  envDefault:"10000"`

	// Cache TTLs.
	CacheTTLHit  time.Duration `env:"CACHE_TTL_HIT"  envDefault:"24h"`
	CacheTTLMiss time.Duration `env:"CACHE_TTL_MISS" envDefault:"5m"`

	// Shutdown.
	ShutdownTimeout time.Duration `env:"SHUTDOWN_TIMEOUT" envDefault:"30s"`

	// Proxy / trusted headers.
	TrustProxy  bool   `env:"TRUST_PROXY"  envDefault:"true"`
	ProxyHeader string `env:"PROXY_HEADER" envDefault:"X-Forwarded-For"`

	// Routing / interstitial (FEATURES_PLAN S2).
	//
	// RoutingEnabled is the feature flag for the rule resolver. When false the
	// handler skips the url:meta / url:rules / url:pixels lookups entirely,
	// preserving the pre-S2 happy path latency.
	RoutingEnabled         bool `env:"ROUTING_ENABLED" envDefault:"true"`
	PixelInterstitialDelay int  `env:"PIXEL_INTERSTITIAL_DELAY_MS" envDefault:"150"`
}

// Load parses the environment into Config.
func Load() (*Config, error) {
	var c Config
	if err := env.Parse(&c); err != nil {
		return nil, fmt.Errorf("config: %w", err)
	}
	return &c, nil
}

// MustLoad panics on error — intended for main().
func MustLoad() *Config {
	c, err := Load()
	if err != nil {
		panic(err)
	}
	return c
}
