// Package events publishes click events to Redis Streams (stream:clicks)
// without blocking the redirect handler.
//
// Design (per INTEGRATION_CONTRACT section 5 + HLA 2.1):
//   - Publish() is non-blocking: select with default branch → drop + counter.
//   - A worker pool drains the buffered channel and issues XADD with
//     MAXLEN ~ 1_000_000 (approx trim, O(1) amortized).
//   - Close() shuts the channel and waits for workers up to a timeout.
package events

import (
	"context"
	"sync"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"

	"github.com/urlshortener/redirect-service/internal/metrics"
)

// Event is the payload XADDed to stream:clicks.
// Field names MUST match INTEGRATION_CONTRACT section 5:
//   code, ts, ip, ua, ref, country, branch
//
// `branch` is the S2 extension: "direct" | "geo" | "device" | "ab_N".
type Event struct {
	Code    string
	TsMs    int64
	IP      string
	UA      string
	Referer string
	Country string
	Branch  string
}

// XAdder is the narrow interface over go-redis that we need. Satisfied by
// *redis.Client and by miniredis-backed clients.
type XAdder interface {
	XAdd(ctx context.Context, a *redis.XAddArgs) *redis.StringCmd
	Incr(ctx context.Context, key string) *redis.IntCmd
	Set(ctx context.Context, key string, value any, expiration time.Duration) *redis.StatusCmd
	Ping(ctx context.Context) *redis.StatusCmd
	Close() error
}

// Publisher streams click events to Redis.
type Publisher struct {
	rdb     XAdder
	stream  string
	maxLen  int64
	ch      chan Event
	workers int
	wg      sync.WaitGroup
	log     zerolog.Logger

	closed atomic.Bool
}

// Config for the Publisher.
type Config struct {
	Stream  string
	MaxLen  int64
	Workers int
	Buffer  int
}

// New constructs a Publisher. Callers must call Start(ctx).
func New(rdb XAdder, cfg Config, log zerolog.Logger) *Publisher {
	if cfg.Workers <= 0 {
		cfg.Workers = 4
	}
	if cfg.Buffer <= 0 {
		cfg.Buffer = 10000
	}
	if cfg.Stream == "" {
		cfg.Stream = "stream:clicks"
	}
	if cfg.MaxLen <= 0 {
		cfg.MaxLen = 1_000_000
	}
	return &Publisher{
		rdb:     rdb,
		stream:  cfg.Stream,
		maxLen:  cfg.MaxLen,
		ch:      make(chan Event, cfg.Buffer),
		workers: cfg.Workers,
		log:     log,
	}
}

// Start spawns the worker pool. Workers exit when the channel is closed
// (via Close) or when ctx is canceled.
func (p *Publisher) Start(ctx context.Context) {
	for i := 0; i < p.workers; i++ {
		p.wg.Add(1)
		go p.worker(ctx, i)
	}
}

// Publish enqueues an event. Non-blocking — drops + increments
// redirect_events_dropped_total when the channel is full.
//
// The redirect hot path calls this; it MUST NOT block.
func (p *Publisher) Publish(e Event) {
	if p.closed.Load() {
		metrics.EventsDropped.Inc()
		return
	}
	select {
	case p.ch <- e:
		metrics.EventsQueueDepth.Set(float64(len(p.ch)))
	default:
		metrics.EventsDropped.Inc()
	}
}

// QueueLen returns the current channel depth (useful for gauges / tests).
func (p *Publisher) QueueLen() int { return len(p.ch) }

// Close stops accepting new events, drains outstanding ones, and waits for
// workers up to timeout. Safe to call multiple times.
func (p *Publisher) Close(timeout time.Duration) error {
	if !p.closed.CompareAndSwap(false, true) {
		return nil
	}
	close(p.ch)

	done := make(chan struct{})
	go func() { p.wg.Wait(); close(done) }()

	select {
	case <-done:
		return nil
	case <-time.After(timeout):
		p.log.Warn().Dur("timeout", timeout).Msg("publisher: shutdown timeout; abandoning in-flight events")
		return context.DeadlineExceeded
	}
}

func (p *Publisher) worker(ctx context.Context, id int) {
	defer p.wg.Done()
	log := p.log.With().Int("worker", id).Logger()

	for {
		select {
		case <-ctx.Done():
			return
		case e, ok := <-p.ch:
			if !ok {
				return
			}
			p.publishOne(ctx, e, log)
			metrics.EventsQueueDepth.Set(float64(len(p.ch)))
		}
	}
}

func (p *Publisher) publishOne(ctx context.Context, e Event, log zerolog.Logger) {
	// Per-XADD timeout so a Redis hiccup can't stall a worker indefinitely.
	xctx, cancel := context.WithTimeout(ctx, 500*time.Millisecond)
	defer cancel()

	branch := e.Branch
	if branch == "" {
		branch = "direct"
	}
	args := &redis.XAddArgs{
		Stream: p.stream,
		MaxLen: p.maxLen,
		Approx: true, // ~ O(1) amortized trim
		Values: map[string]any{
			"code":    e.Code,
			"ts":      e.TsMs,
			"ip":      e.IP,
			"ua":      e.UA,
			"ref":     e.Referer,
			"country": e.Country,
			"branch":  branch,
		},
	}
	if err := p.rdb.XAdd(xctx, args).Err(); err != nil {
		metrics.EventsFailed.Inc()
		metrics.Errors.WithLabelValues("stream").Inc()
		log.Warn().Err(err).Str("code", e.Code).Msg("xadd failed")
		return
	}
	metrics.EventsPublished.Inc()

	// Real-time click counter — api-service reads `clicks:{code}` and
	// merges with the Postgres baseline for the UI. Fire-and-forget.
	_ = p.rdb.Incr(xctx, "clicks:"+e.Code).Err()
	_ = p.rdb.Set(xctx, "clicks:last:"+e.Code, e.TsMs, 30*24*time.Hour).Err()
}
