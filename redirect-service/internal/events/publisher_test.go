package events_test

import (
	"context"
	"io"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"

	"github.com/urlshortener/redirect-service/internal/events"
)

func newPublisher(t *testing.T, buf, workers int) (*events.Publisher, *miniredis.Miniredis, *redis.Client) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	p := events.New(rdb, events.Config{
		Stream:  "stream:clicks",
		MaxLen:  1000,
		Workers: workers,
		Buffer:  buf,
	}, zerolog.New(io.Discard))
	return p, mr, rdb
}

func TestPublisher_HappyPath(t *testing.T) {
	t.Parallel()
	p, mr, _ := newPublisher(t, 16, 2)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	p.Start(ctx)

	p.Publish(events.Event{Code: "aB3xK9", TsMs: time.Now().UnixMilli(), IP: "1.2.3.4", Country: "US"})

	require.Eventually(t, func() bool {
		return mr.Exists("stream:clicks")
	}, 2*time.Second, 20*time.Millisecond, "stream should be created")

	require.NoError(t, p.Close(2*time.Second))
}

func TestPublisher_DropsWhenFull(t *testing.T) {
	t.Parallel()
	// No workers => channel never drains => easy backpressure test.
	p, _, _ := newPublisher(t, 2, 0)

	// Fill the buffer + overflow.
	p.Publish(events.Event{Code: "a"})
	p.Publish(events.Event{Code: "b"})
	p.Publish(events.Event{Code: "c"}) // dropped
	p.Publish(events.Event{Code: "d"}) // dropped

	require.Equal(t, 2, p.QueueLen(), "buffer cap should hold 2 events exactly")
	require.NoError(t, p.Close(500*time.Millisecond))
}

func TestPublisher_PublishAfterCloseDrops(t *testing.T) {
	t.Parallel()
	p, _, _ := newPublisher(t, 4, 1)
	ctx := context.Background()
	p.Start(ctx)
	require.NoError(t, p.Close(time.Second))

	// Must not panic or block.
	p.Publish(events.Event{Code: "post-close"})
}
