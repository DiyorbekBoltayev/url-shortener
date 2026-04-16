"""Prometheus metrics + HTTP exporter server.

Exposed on settings.metrics_port (default :9091) per INTEGRATION_CONTRACT.md section 10.
"""
from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

# Dedicated registry so tests can construct a fresh one; app uses module globals.
REGISTRY = CollectorRegistry(auto_describe=True)

EVENTS_CONSUMED = Counter(
    "events_consumed_total",
    "Stream entries pulled via XREADGROUP",
    registry=REGISTRY,
)
EVENTS_ENRICHED = Counter(
    "events_enriched_total",
    "Stream entries successfully enriched into row tuples",
    registry=REGISTRY,
)
EVENTS_DROPPED = Counter(
    "events_dropped_total",
    "Stream entries dropped (reason=bad_payload|poison|enrich_error|dead_letter)",
    labelnames=("reason",),
    registry=REGISTRY,
)
EVENTS_FLUSHED = Counter(
    "events_flushed_total",
    "Rows durably inserted into ClickHouse (post-XACK)",
    registry=REGISTRY,
)
EVENTS_RECLAIMED = Counter(
    "events_reclaimed_total",
    "Entries reclaimed via XAUTOCLAIM / XCLAIM from dead consumers",
    registry=REGISTRY,
)
BATCH_SIZE = Histogram(
    "batch_size_rows",
    "Rows per ClickHouse flush",
    buckets=(1, 10, 50, 100, 250, 500, 1000, 2500, 5000),
    registry=REGISTRY,
)
FLUSH_DURATION = Histogram(
    "flush_duration_seconds",
    "Wall-clock time of ClickHouse INSERT + XACK",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)
CLICKHOUSE_INSERT_ERRORS = Counter(
    "clickhouse_insert_errors_total",
    "Final failures of the ClickHouse insert (post-retry)",
    registry=REGISTRY,
)
QUEUE_LAG_MS = Gauge(
    "queue_lag_ms",
    "Age (ms) of the oldest pending entry in the consumer-group PEL",
    registry=REGISTRY,
)
LAST_FLUSH_TS = Gauge(
    "last_successful_flush_timestamp",
    "Unix epoch seconds of the last successful CH insert+XACK",
    registry=REGISTRY,
)


def start_metrics_server(port: int) -> None:
    """Start the prometheus_client HTTP exporter on 0.0.0.0:port."""
    start_http_server(port, registry=REGISTRY)
