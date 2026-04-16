// Package metrics defines the Prometheus collectors exported by redirect-service.
//
// Cardinality rules:
//   - status labels are bucketed to a small fixed set (e.g. 302, 404, 410, 451,
//     500, 503); never the raw short code.
//   - no URL / user labels.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Registry is this service's private registry. We do not use the default
// global registry so that tests can instantiate multiple instances safely.
var Registry = prometheus.NewRegistry()

var (
	// RedirectRequests counts redirect endpoint outcomes by HTTP status.
	RedirectRequests = promauto.With(Registry).NewCounterVec(
		prometheus.CounterOpts{
			Name: "redirect_requests_total",
			Help: "Total redirect requests by HTTP status code.",
		},
		[]string{"status"},
	)

	// RedirectLatency is the end-to-end handler latency histogram.
	// Buckets: 0.5ms..1s, tight around the p99 budget of 5ms.
	RedirectLatency = promauto.With(Registry).NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "redirect_latency_seconds",
			Help:    "Redirect handler latency in seconds.",
			Buckets: []float64{0.0005, 0.001, 0.002, 0.003, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 1},
		},
		[]string{"status"},
	)

	// CacheHits / CacheMisses track Redis lookup outcomes.
	CacheHits = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Name: "redirect_cache_hits_total",
		Help: "Redis cache hits.",
	})
	CacheMisses = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Name: "redirect_cache_misses_total",
		Help: "Redis cache misses (forcing Postgres lookup).",
	})

	// PGFallback counts PG lookups triggered by a cache miss.
	PGFallback = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Name: "redirect_pg_fallback_total",
		Help: "Postgres lookups after a cache miss.",
	})

	// Events — click stream publisher.
	EventsPublished = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Name: "redirect_events_published_total",
		Help: "Click events successfully XADDed to stream:clicks.",
	})
	EventsDropped = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Name: "redirect_events_dropped_total",
		Help: "Click events dropped because the publisher queue was full.",
	})
	EventsFailed = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Name: "redirect_events_failed_total",
		Help: "Click events that failed to XADD (Redis error).",
	})
	EventsQueueDepth = promauto.With(Registry).NewGauge(prometheus.GaugeOpts{
		Name: "redirect_events_queue_depth",
		Help: "Current depth of the publisher channel.",
	})

	// Errors by source.
	Errors = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Name: "redirect_errors_total",
		Help: "Errors by source (cache|db|stream|geoip|handler).",
	}, []string{"source"})

	// RouteBranch counts redirect outcomes by routing branch
	// (direct | geo | device | ab_N). Cardinality is bounded by the number
	// of A/B variants per link (typically ≤ 5).
	RouteBranch = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Name: "redirect_route_branch_total",
		Help: "Redirect outcomes by routing rule branch.",
	}, []string{"branch"})

	// InterstitialServed counts HTML interstitial responses (pixel firing path).
	InterstitialServed = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Name: "redirect_interstitial_served_total",
		Help: "Pixel interstitial HTML responses served in place of 302.",
	})
)
