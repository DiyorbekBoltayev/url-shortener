// Package cache implements the Redis cache-aside layer for short codes.
//
// Key format follows HLA section 2.1: `url:<short_code>` → `<long_url>`.
// That contract stores *only the long URL* as the value, with a 24h TTL.
// A negative-cache sentinel (`__MISS__`) is stored for unknown codes to
// avoid hammering Postgres when bots probe random codes.
package cache

import (
	"context"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	// KeyPrefix is the Redis key prefix for short-code lookups.
	KeyPrefix = "url:"
	// SentinelMiss marks a negatively-cached "not found".
	SentinelMiss = "__MISS__"
)

// ErrNotFound indicates a negative-cache hit (known missing code).
var ErrNotFound = errors.New("cache: code known-missing")

// ErrCacheMiss indicates the key is absent — caller should query Postgres.
// Thin alias over redis.Nil so callers don't have to import go-redis.
var ErrCacheMiss = redis.Nil

// Client is the minimal subset of *redis.Client we need — makes testing
// with miniredis or fakes straightforward.
type Client interface {
	Get(ctx context.Context, key string) *redis.StringCmd
	Set(ctx context.Context, key string, value any, expiration time.Duration) *redis.StatusCmd
	HMGet(ctx context.Context, key string, fields ...string) *redis.SliceCmd
	Ping(ctx context.Context) *redis.StatusCmd
	Close() error
}

// Cache wraps a Redis client and provides the cache-aside operations.
type Cache struct {
	rdb     Client
	ttlHit  time.Duration
	ttlMiss time.Duration
}

// New constructs a Cache. ttlMiss==0 disables negative caching.
func New(rdb Client, ttlHit, ttlMiss time.Duration) *Cache {
	return &Cache{rdb: rdb, ttlHit: ttlHit, ttlMiss: ttlMiss}
}

// Get returns the long URL for code.
//
// Return values:
//   - (url, nil)              — cache hit.
//   - ("", ErrNotFound)       — negative-cache hit.
//   - ("", ErrCacheMiss)      — key absent (caller should hit PG).
//   - ("", other)             — transport error.
func (c *Cache) Get(ctx context.Context, code string) (string, error) {
	v, err := c.rdb.Get(ctx, KeyPrefix+code).Result()
	if err != nil {
		return "", err
	}
	if v == SentinelMiss {
		return "", ErrNotFound
	}
	return v, nil
}

// SetHit stores the long URL with the hit TTL.
func (c *Cache) SetHit(ctx context.Context, code, longURL string) error {
	return c.rdb.Set(ctx, KeyPrefix+code, longURL, c.ttlHit).Err()
}

// SetMiss stores the negative-cache sentinel. No-op if ttlMiss <= 0.
func (c *Cache) SetMiss(ctx context.Context, code string) error {
	if c.ttlMiss <= 0 {
		return nil
	}
	return c.rdb.Set(ctx, KeyPrefix+code, SentinelMiss, c.ttlMiss).Err()
}

// Ping is a thin wrapper for healthchecks.
func (c *Cache) Ping(ctx context.Context) error {
	return c.rdb.Ping(ctx).Err()
}

// Meta is the decoded projection of the `url:meta:{code}` HASH maintained by
// api-service (FEATURES_PLAN "Redis cache row enrichment").
//
// Fields we currently care about:
//
//	has_rules   — "1" when the link has routing rules
//	has_pixels  — "1" when the link has at least one retarget pixel
//
// Additional fields (expires_at, password_hash, is_active, max_clicks,
// safety_status) are populated when present but not consumed by the redirect
// hot path yet; the URL gate logic still relies on Postgres-backed data in
// store.URL. Keeping them parsed here makes future wiring trivial.
type Meta struct {
	HasRules     bool
	HasPixels    bool
	SafetyStatus string
}

// metaKey is the key shape documented in FEATURES_PLAN ("Redis cache row
// enrichment"): `url:meta:{code}` HASH.
func metaKey(code string) string { return KeyPrefix + "meta:" + code }

// rulesKey returns the cache key for decoded routing rules.
func rulesKey(code string) string { return KeyPrefix + "rules:" + code }

// pixelsKey returns the cache key for the pixel array.
func pixelsKey(code string) string { return KeyPrefix + "pixels:" + code }

// GetMeta fetches the `url:meta:{code}` HASH fields we care about. Missing
// keys and missing fields are treated as zero-value — a redirect for a link
// without rules/pixels stays on the happy path.
//
// Returns (nil, nil) when the hash does not exist.
func (c *Cache) GetMeta(ctx context.Context, code string) (*Meta, error) {
	fields := []string{"has_rules", "has_pixels", "safety_status"}
	vs, err := c.rdb.HMGet(ctx, metaKey(code), fields...).Result()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return nil, nil
		}
		return nil, err
	}
	// HMGet returns nils for absent fields. If every field is nil, the hash is
	// effectively missing — skip allocation.
	allNil := true
	for _, v := range vs {
		if v != nil {
			allNil = false
			break
		}
	}
	if allNil {
		return nil, nil
	}
	m := &Meta{}
	if len(vs) > 0 {
		if s, ok := vs[0].(string); ok {
			m.HasRules = s == "1" || s == "true"
		}
	}
	if len(vs) > 1 {
		if s, ok := vs[1].(string); ok {
			m.HasPixels = s == "1" || s == "true"
		}
	}
	if len(vs) > 2 {
		if s, ok := vs[2].(string); ok {
			m.SafetyStatus = s
		}
	}
	return m, nil
}

// GetRules fetches the raw JSON at `url:rules:{code}`. Returns ("", nil) when
// the key is missing so callers can treat absence as "no rules".
func (c *Cache) GetRules(ctx context.Context, code string) (string, error) {
	v, err := c.rdb.Get(ctx, rulesKey(code)).Result()
	if errors.Is(err, redis.Nil) {
		return "", nil
	}
	return v, err
}

// GetPixels fetches the raw JSON at `url:pixels:{code}`. Returns ("", nil)
// when the key is missing.
func (c *Cache) GetPixels(ctx context.Context, code string) (string, error) {
	v, err := c.rdb.Get(ctx, pixelsKey(code)).Result()
	if errors.Is(err, redis.Nil) {
		return "", nil
	}
	return v, err
}
