# analytics-worker

Python 3.12 async microservice that consumes click events from **Redis Streams**
(published by the Go `redirect-service`), enriches them (GeoIP + UA + bot
detection + referer classification), batches, and bulk-inserts into
**ClickHouse**.

- **At-least-once** delivery via Redis consumer groups (`XREADGROUP` / `XACK`).
- **Effectively-once** at the sink via ClickHouse `ReplacingMergeTree`
  deduplication on `stream_id`.
- **Crash recovery** via periodic `XAUTOCLAIM` of dead-consumer PEL entries.
- Stack: `redis[hiredis] 5.2`, `clickhouse-connect 0.8`, `ua-parser[regex] 1.0`
  (**not** the abandoned `user-agents` wrapper), `geoip2 5.2`, `structlog 24.4`,
  `prometheus-client`, `pydantic-settings`, `tenacity`.

> Integration contract (stream name, consumer group, env vars) is binding and
> owned by `INTEGRATION_CONTRACT.md` at the repository root. Do not drift.

## Architecture

```
redirect-service  --XADD stream:clicks-->  redis-app:6380
                                             |
                                             | XREADGROUP analytics
                                             v
                                   +-------------------------+
                                   |    analytics-worker     |
                                   |                         |
                                   |  consumer  --enrich-->  |
                                   |     |                   |
                                   |     v                   |
                                   |   buffer (<=1000, <=1s) |
                                   |     |                   |
                                   |     v                   |
                                   |  ClickHouse INSERT      |
                                   |     |                   |
                                   |     v                   |
                                   |   XACK ids              |
                                   |                         |
                                   |  pel-reclaimer (60s):   |
                                   |   XAUTOCLAIM idle>5m -> |
                                   |   replay                |
                                   +-------------------------+
                                             |
                                             v
                                         clickhouse:8123 (http)
                                             |
                                          clicks table
                                        (ReplacingMergeTree)
```

## Run locally (dev)

Prereqs: `uv`, `python 3.12`, running `redis-app` (port 6380), `clickhouse`,
and a MaxMind `GeoLite2-City.mmdb` on disk (or worker will no-op geo lookups).

```bash
cp .env.example .env
# edit .env if needed
make install
make run
```

## Run via Docker Compose

The compose file assumes the shared external network + volume from the
`infrastructure` repo:

```bash
# One-time, from the infrastructure repo:
# docker network create --driver bridge --subnet 172.28.0.0/16 url-shortener-net
# docker volume create urlshortener-geoip-data

cp .env.example .env
make build up
make logs
# Scale horizontally:
make scale N=2
```

## ClickHouse schema

The worker expects the `clicks` table to exist (created by the `infrastructure`
repo, not here). Target schema:

```sql
CREATE TABLE IF NOT EXISTS clicks (
    event_time          DateTime64(3, 'UTC'),
    short_code          LowCardinality(String),
    ip_hash             FixedString(32),
    country_code        LowCardinality(String),
    country_name        String,
    region              String,
    city                String,
    lat                 Float32,
    lon                 Float32,
    ua_browser          LowCardinality(String),
    ua_browser_version  String,
    ua_os               LowCardinality(String),
    ua_os_version       String,
    ua_device           LowCardinality(String),
    is_bot              UInt8,
    referer             String,
    referer_domain      LowCardinality(String),
    referer_type        LowCardinality(String),
    stream_id           String
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (short_code, event_time, stream_id);
```

## Stream contract

Produced by `redirect-service`:

```
XADD stream:clicks MAXLEN ~ 1000000 * \
  code <short_code> \
  ts <unix_ms> \
  ip <client_ip> \
  ua <user_agent> \
  ref <referer> \
  country <country_code>
```

Consumer group: **`analytics`** (locked by INTEGRATION_CONTRACT.md).

## Observability

- **Metrics:** `:9091/metrics` (Prometheus scrape target; see HLA section 10).
- **Health:** `:9092/-/healthy` (200 OK / 503 stale after 60s without flush).
- **Logs:** JSON, stdout, `structlog`. Bound field: `service=analytics-worker`.

Key metrics:

| Metric | Type | Meaning |
|---|---|---|
| `events_consumed_total` | Counter | entries pulled from stream |
| `events_enriched_total` | Counter | entries enriched into rows |
| `events_flushed_total` | Counter | rows durably written to CH |
| `events_dropped_total{reason}` | Counter | dropped (bad_payload / enrich_error / dead_letter) |
| `events_reclaimed_total` | Counter | entries recovered via XAUTOCLAIM |
| `batch_size_rows` | Histogram | rows per CH flush |
| `flush_duration_seconds` | Histogram | CH insert + XACK wall time |
| `clickhouse_insert_errors_total` | Counter | final failures post-retry |
| `queue_lag_ms` | Gauge | age of oldest PEL entry |
| `last_successful_flush_timestamp` | Gauge | readiness signal |

## Configuration

All settings via environment variables or `.env` (pydantic-settings).
See `.env.example`. Integration-mandated defaults:

| Var | Default | Locked by contract |
|---|---|---|
| `REDIS_STREAM_URL` | `redis://redis-app:6380/0` | yes |
| `STREAM_NAME` | `stream:clicks` | **yes** |
| `CONSUMER_GROUP` | `analytics` | **yes** |
| `BATCH_SIZE` | `1000` | yes |
| `FLUSH_INTERVAL_SEC` | `1.0` | yes |
| `CLICKHOUSE_HOST` | `clickhouse` | yes |
| `CLICKHOUSE_DB` | `analytics` | yes |
| `GEOIP_DB_PATH` | `/data/GeoLite2-City.mmdb` | yes |

## Testing

```bash
make test
```

Uses `fakeredis[lua]` for `XREADGROUP`/`XACK`/`XPENDING` semantics and a mock
ClickHouse client. Covers: bot detector patterns, enricher, batch writer
(size/time/drain triggers, no-XACK-on-failure, XACK-after-insert), and the
XREADGROUP consumer loop.

## Windows notes

- `uvloop` is not available on Windows; the worker falls back to the stdlib
  asyncio loop automatically.
- `asyncio.loop.add_signal_handler` is not supported on Windows. On Windows
  the worker relies on `KeyboardInterrupt` (Ctrl+C) for shutdown instead of
  SIGTERM. In Docker (Linux containers) signals work normally.

## Delivery semantics

Redis Streams is **at-least-once**. Two crash windows exist:

1. Crash after CH insert, before `XACK` -> replayed on restart/reclaim;
   `ReplacingMergeTree.stream_id` dedupes at merge.
2. Crash after pull, before CH insert -> reclaimed after `PEL_IDLE_MS` (default
   5 min) by the pel-reclaimer, replayed.

Do not promise exactly-once. Dashboards that need accurate counts should use
`SELECT ... FINAL` or `uniqExact(stream_id)`.

## License

MIT. See `LICENSE`.
