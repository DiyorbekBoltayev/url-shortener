package cache_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"

	"github.com/urlshortener/redirect-service/internal/cache"
)

func newTestCache(t *testing.T) (*cache.Cache, *miniredis.Miniredis, *redis.Client) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	return cache.New(rdb, 24*time.Hour, 5*time.Minute), mr, rdb
}

func TestCache_GetSetHit(t *testing.T) {
	t.Parallel()
	c, mr, _ := newTestCache(t)
	ctx := context.Background()

	// Miss (absent)
	_, err := c.Get(ctx, "abc")
	require.ErrorIs(t, err, cache.ErrCacheMiss)

	// Populate
	require.NoError(t, c.SetHit(ctx, "abc", "https://example.com"))

	// Hit
	v, err := c.Get(ctx, "abc")
	require.NoError(t, err)
	require.Equal(t, "https://example.com", v)

	// TTL respected
	ttl := mr.TTL(cache.KeyPrefix + "abc")
	require.Greater(t, ttl, 23*time.Hour)
}

func TestCache_NegativeCache(t *testing.T) {
	t.Parallel()
	c, _, _ := newTestCache(t)
	ctx := context.Background()

	require.NoError(t, c.SetMiss(ctx, "ghost"))
	_, err := c.Get(ctx, "ghost")
	require.True(t, errors.Is(err, cache.ErrNotFound), "expected ErrNotFound, got %v", err)
}

func TestCache_Ping(t *testing.T) {
	t.Parallel()
	c, _, _ := newTestCache(t)
	require.NoError(t, c.Ping(context.Background()))
}
