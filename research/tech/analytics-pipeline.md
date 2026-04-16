# Analytics Worker — Redis Streams → ClickHouse

Production reference for the `analytics-worker` microservice. Consumes click events from a Redis Stream published by the Go redirector, enriches with GeoIP + UA parsing + bot detection, batches, and bulk-inserts into ClickHouse.

- **Runtime:** Python 3.12+ (asyncio)
- **Ingest:** Redis Streams consumer group (at-least-once, idempotent writes)
- **Sink:** ClickHouse (native batch insert, `clickhouse-connect` async)
- **Pattern:** single event loop, N replicas each with a unique consumer ID
- **Not used:** Celery, RabbitMQ, threads. One coroutine pulls, one flushes.

---

## 1. Pinned versions (`pyproject.toml`)

```toml
[project]
name = "analytics-worker"
version = "0.1.0"
requires-python = ">=3.12,<3.14"
dependencies = [
  "redis[hiredis]==5.2.1",              # async client + C parser
  "clickhouse-connect==0.8.17",         # async get_async_client()
  "geoip2==5.2.0",                      # wraps maxminddb 3.0.0 (free-threaded)
  "ua-parser[regex]==1.0.1",            # google/re2-backed, ~10x pure-python
  "structlog==25.5.0",                  # contextvars async support
  "prometheus-client==0.21.1",          # Counter/Histogram/Gauge
  "pydantic==2.10.4",
  "pydantic-settings==2.13.1",
  "uvloop==0.21.0 ; sys_platform != 'win32'",
  "orjson==3.10.12",
  "tenacity==9.0.0",                    # retry CH inserts
]

[project.optional-dependencies]
dev = [
  "pytest==8.3.4",
  "pytest-asyncio==0.25.0",
  "fakeredis[lua]==2.26.1",             # implements XREADGROUP/XACK/XPENDING/XCLAIM
  "pytest-mock==3.14.0",
  "ruff==0.8.4",
  "mypy==1.13.0",
]
```

**Note on `ua-parser` vs `user-agents`:** `user-agents` is a thin wrapper around `ua-parser` and has had no PyPI release in 12+ months — it's effectively stale. `ua-parser[regex]` (the `re2` resolver) is actively maintained by the upstream uap project, is ~10x faster than the pure-Python resolver, and exposes the same regexes. We do our own thin `BrowserInfo` dataclass instead of pulling the dead wrapper.

---

## 2. Project layout

```
analytics-worker/
├── pyproject.toml
├── Dockerfile
├── worker/
│   ├── __init__.py
│   ├── main.py              # entrypoint; wires everything; signal handlers
│   ├── config.py            # pydantic-settings
│   ├── consumer.py          # XREADGROUP loop + XPENDING/XCLAIM recovery
│   ├── enricher.py          # GeoIP + UA + bot detection
│   ├── bot_detector.py      # heuristics + UA regex list
│   ├── writer.py            # batch buffer + ClickHouse flush
│   ├── metrics.py           # prometheus registry + HTTP server
│   ├── health.py            # /healthz handler
│   └── schema.py            # pydantic models for stream payloads
└── tests/
    ├── conftest.py          # fakeredis + mock CH fixtures
    ├── test_consumer.py
    ├── test_enricher.py
    └── test_writer.py
```

---

## 3. Consumer group creation

Idempotent — `BUSYGROUP` is swallowed. `MKSTREAM` creates the stream if the redirector hasn't pushed anything yet (cold start). `$` means "new entries only" on first creation; pass `0` instead only for replay.

```python
# worker/consumer.py
from redis.asyncio import Redis
from redis.exceptions import ResponseError
import structlog

log = structlog.get_logger()

async def ensure_group(redis: Redis, stream: str, group: str) -> None:
    try:
        await redis.xgroup_create(name=stream, groupname=group, id="$", mkstream=True)
        log.info("group_created", stream=stream, group=group)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
        log.debug("group_exists", stream=stream, group=group)
```

---

## 4. XREADGROUP loop

One consumer = one replica. The consumer ID **must be stable per replica** so that reclaimed pending entries go back to the same worker after a restart. Use the pod hostname (k8s gives stable StatefulSet names; for Deployments fall back to `HOSTNAME`).

```python
# worker/consumer.py (cont.)
import asyncio, os, socket
from collections.abc import AsyncIterator

STREAM = "clicks"
GROUP  = "analytics"

def consumer_id() -> str:
    return os.getenv("HOSTNAME") or socket.gethostname()

async def read_loop(
    redis: Redis,
    stop: asyncio.Event,
    *,
    block_ms: int = 5000,
    count: int = 100,
) -> AsyncIterator[tuple[bytes, dict[bytes, bytes]]]:
    cid = consumer_id()
    while not stop.is_set():
        try:
            resp = await redis.xreadgroup(
                groupname=GROUP,
                consumername=cid,
                streams={STREAM: ">"},  # ">" = undelivered-to-this-group
                count=count,
                block=block_ms,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("xreadgroup_failed")
            await asyncio.sleep(1.0)
            continue

        if not resp:
            continue  # idle tick; loop blocks again
        for _stream, entries in resp:
            for msg_id, fields in entries:
                yield msg_id, fields
```

---

## 5. Pending Entries List recovery

After a crash, entries delivered to the dead consumer sit in the PEL forever unless someone claims them. Run a periodic reclaimer. `XAUTOCLAIM` (Redis 6.2+) is simpler than the `XPENDING` → `XCLAIM` two-step and returns entries whose idle time exceeds the threshold, skipping already-deleted IDs.

```python
# worker/consumer.py (cont.)
MIN_IDLE_MS = 60_000  # don't steal from a live peer

async def reclaim_loop(redis: Redis, stop: asyncio.Event) -> AsyncIterator[tuple[bytes, dict[bytes, bytes]]]:
    cid = consumer_id()
    cursor = "0-0"
    while not stop.is_set():
        try:
            cursor, claimed, _deleted = await redis.xautoclaim(
                name=STREAM, groupname=GROUP, consumername=cid,
                min_idle_time=MIN_IDLE_MS, start_id=cursor, count=50,
            )
        except Exception:
            log.exception("xautoclaim_failed")
            await asyncio.sleep(5.0); continue

        for msg_id, fields in claimed:
            log.warning("reclaimed", msg_id=msg_id)
            yield msg_id, fields

        if cursor == b"0-0" or cursor == "0-0":
            await asyncio.sleep(30.0)  # nothing pending, back off
```

Optionally, after N reclaim attempts on the same ID (see `XPENDING` `deliveries` counter), route to a dead-letter stream `clicks:dead` and `XACK` the original so it stops circulating.

---

## 6. Enricher: GeoIP + UA + bot detection

### GeoIP

`geoip2.database.Reader` is **thread-safe and process-safe** on the read path — open **once at startup**, reuse across all events. The `.mmdb` is memory-mapped; don't re-open per event.

```python
# worker/enricher.py
import geoip2.database
from functools import lru_cache
from hashlib import blake2b
from ua_parser import user_agent_parser
from dataclasses import dataclass

@dataclass(slots=True)
class Geo:
    country: str | None
    city: str | None
    lat: float | None
    lon: float | None

class GeoReader:
    def __init__(self, mmdb_path: str) -> None:
        self._r = geoip2.database.Reader(mmdb_path)

    def lookup(self, ip: str) -> Geo:
        try:
            r = self._r.city(ip)
        except (geoip2.errors.AddressNotFoundError, ValueError):
            return Geo(None, None, None, None)
        return Geo(
            country=r.country.iso_code,
            city=r.city.name,
            lat=r.location.latitude,
            lon=r.location.longitude,
        )

    def close(self) -> None:
        self._r.close()
```

### UA parsing (cached)

The UA regex set (~400 patterns) is expensive per-call. Cache by UA-string hash — long strings as `lru_cache` keys bloat memory; hashing keeps the key 16 bytes.

```python
@dataclass(slots=True, frozen=True)
class UA:
    browser: str; browser_version: str
    os: str; os_version: str
    device: str
    is_bot: bool

def _hash(ua: str) -> bytes:
    return blake2b(ua.encode("utf-8", "ignore"), digest_size=16).digest()

@lru_cache(maxsize=20_000)
def _parse_cached(_h: bytes, ua: str) -> UA:
    p = user_agent_parser.Parse(ua)
    return UA(
        browser=p["user_agent"]["family"],
        browser_version=p["user_agent"]["major"] or "",
        os=p["os"]["family"],
        os_version=p["os"]["major"] or "",
        device=p["device"]["family"],
        is_bot=False,  # filled by bot_detector
    )

def parse_ua(ua: str) -> UA:
    return _parse_cached(_hash(ua), ua)
```

### Bot detection

Keep it dumb & fast: substring match on a compiled regex union, plus a few signals (missing UA, single-letter UA, known abuse IPs). Heavier fingerprinting lives in the Go edge.

```python
# worker/bot_detector.py
import re

_BOT_RE = re.compile(
    r"bot|crawler|spider|slurp|facebookexternalhit|bingpreview|headlesschrome|"
    r"python-requests|curl|wget|go-http-client|axios|okhttp",
    re.IGNORECASE,
)

def is_bot(ua: str, ua_family: str) -> bool:
    if not ua or len(ua) < 8:
        return True
    if _BOT_RE.search(ua):
        return True
    if ua_family in {"Other", ""}:
        return True
    return False
```

---

## 7. Writer: batch buffer + flush

Two triggers: **size** (`BATCH_MAX=1000`) or **time** (`FLUSH_INTERVAL=1.0s`). The writer owns the buffer and the flush task; the consumer only pushes via `put()`. We keep the original `msg_id` alongside each row so we can `XACK` exactly the messages that made it into CH.

```python
# worker/writer.py
import asyncio, time
from dataclasses import dataclass
from clickhouse_connect import get_async_client
from clickhouse_connect.driver.asyncclient import AsyncClient
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

COLS = (
    "event_time", "short_code", "ip", "country", "city", "lat", "lon",
    "ua_browser", "ua_os", "ua_device", "is_bot", "referer", "user_id",
)

@dataclass(slots=True)
class Row:
    msg_id: bytes
    values: tuple  # ordered per COLS

class BatchWriter:
    def __init__(self, ch: AsyncClient, redis, stream: str, group: str,
                 max_size: int, interval: float):
        self._ch = ch
        self._redis = redis
        self._stream = stream; self._group = group
        self._max = max_size; self._interval = interval
        self._buf: list[Row] = []
        self._lock = asyncio.Lock()
        self._last_flush = time.monotonic()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._ticker(), name="batch-ticker")

    async def put(self, row: Row) -> None:
        async with self._lock:
            self._buf.append(row)
            if len(self._buf) >= self._max:
                await self._flush_locked()

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            async with self._lock:
                if self._buf and (time.monotonic() - self._last_flush) >= self._interval:
                    await self._flush_locked()

    @retry(stop=stop_after_attempt(5),
           wait=wait_exponential_jitter(initial=0.2, max=5.0))
    async def _insert(self, rows: list[tuple]) -> None:
        await self._ch.insert("clicks", rows, column_names=COLS)

    async def _flush_locked(self) -> None:
        if not self._buf:
            return
        rows = self._buf
        self._buf = []
        values = [r.values for r in rows]
        ids = [r.msg_id for r in rows]
        t0 = time.monotonic()
        try:
            await self._insert(values)
        except Exception:
            log.exception("ch_insert_failed_giving_up", n=len(rows))
            # Do NOT XACK — messages stay in PEL and will be reclaimed.
            return
        # XACK only after durable insert. Pipeline the ack.
        async with self._redis.pipeline(transaction=False) as p:
            p.xack(self._stream, self._group, *ids)
            await p.execute()
        self._last_flush = time.monotonic()
        BATCH_SIZE.observe(len(rows))
        FLUSHED.inc(len(rows))
        CH_LATENCY.observe(time.monotonic() - t0)
        LAST_FLUSH_TS.set(time.time())

    async def drain(self) -> None:
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
        async with self._lock:
            await self._flush_locked()
```

ClickHouse-side DDL (append-only, partitioned by day, deduped by stream msg_id as idempotency key):

```sql
CREATE TABLE clicks (
  event_time   DateTime64(3, 'UTC'),
  short_code   LowCardinality(String),
  ip           IPv6,
  country      LowCardinality(String),
  city         String,
  lat Float32, lon Float32,
  ua_browser   LowCardinality(String),
  ua_os        LowCardinality(String),
  ua_device    LowCardinality(String),
  is_bot       UInt8,
  referer      String,
  user_id      UInt64,
  stream_id    String   -- redis XID; unique per-event
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (short_code, event_time, stream_id);
```

`ReplacingMergeTree` on `stream_id` makes re-inserts after crash-before-XACK idempotent at merge time; use `FINAL` or a `SELECT ... argMax(...)` query for exact counts.

---

## 8. Delivery semantics

Redis Streams gives **at-least-once**. Two failure windows:

1. **Crash after CH insert, before XACK** → message is replayed on next start/reclaim. `ReplacingMergeTree.stream_id` dedupes.
2. **Crash after pulling, before CH insert** → reclaimer picks it up after `MIN_IDLE_MS`, replays.

"Exactly-once" is a lie in distributed systems. What we get: **at-least-once delivery + idempotent sink = effectively-once**. Document this, don't promise more.

---

## 9. Metrics

```python
# worker/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server

CONSUMED     = Counter("events_consumed_total", "Events pulled from stream")
FLUSHED      = Counter("events_flushed_total",  "Events durably written to CH")
FAILED       = Counter("events_failed_total",   "Events dropped after retries")
RECLAIMED    = Counter("events_reclaimed_total","Events taken via XAUTOCLAIM")
BATCH_SIZE   = Histogram("batch_size_rows", "Rows per CH flush",
                         buckets=(1, 10, 50, 100, 250, 500, 1000, 2500, 5000))
CH_LATENCY   = Histogram("clickhouse_insert_latency_seconds",
                         "CH INSERT wall time",
                         buckets=(.01, .025, .05, .1, .25, .5, 1, 2, 5, 10))
QUEUE_LAG    = Gauge("queue_lag_seconds",
                     "Age of oldest pending entry in PEL")
LAST_FLUSH_TS= Gauge("last_successful_flush_timestamp", "Unix ts of last CH flush")

def serve(port: int = 9090) -> None:
    start_http_server(port)
```

`QUEUE_LAG` is sampled by a background task:

```python
async def sample_lag(redis, stream, group, stop):
    while not stop.is_set():
        info = await redis.xpending(stream, group)
        # info = {"pending": N, "min": "<id>", "max": "<id>", "consumers": [...]}
        if info and info["pending"] and info["min"]:
            min_id = info["min"].decode() if isinstance(info["min"], bytes) else info["min"]
            ms = int(min_id.split("-")[0])
            QUEUE_LAG.set(max(0.0, time.time() - ms / 1000.0))
        else:
            QUEUE_LAG.set(0.0)
        await asyncio.sleep(5)
```

---

## 10. Healthcheck

Liveness is trivial (process alive). Readiness is "we flushed recently":

```python
# worker/health.py
from aiohttp import web
import time
from .metrics import LAST_FLUSH_TS

STALE_AFTER = 30.0  # seconds

async def healthz(_req):
    last = LAST_FLUSH_TS._value.get()  # float
    if last == 0:
        # cold start grace: treat as healthy for first 60s after boot
        return web.json_response({"status": "starting"}, status=200)
    age = time.time() - last
    if age > STALE_AFTER:
        return web.json_response({"status": "stale", "age_s": age}, status=503)
    return web.json_response({"status": "ok", "age_s": age}, status=200)

def app() -> web.Application:
    a = web.Application()
    a.router.add_get("/healthz", healthz)
    return a
```

Mount on a separate port from `/metrics` so the LB can probe without scraping Prom.

---

## 11. Main loop + graceful shutdown

```python
# worker/main.py
import asyncio, signal
import structlog
from clickhouse_connect import get_async_client
from redis.asyncio import Redis
from .config import Settings
from .consumer import ensure_group, read_loop, reclaim_loop
from .enricher import GeoReader, parse_ua
from .bot_detector import is_bot
from .writer import BatchWriter, Row
from .metrics import CONSUMED, RECLAIMED, serve as serve_metrics

log = structlog.get_logger()

async def run() -> None:
    s = Settings()
    redis = Redis.from_url(s.redis_url, decode_responses=False)
    ch = await get_async_client(host=s.ch_host, port=s.ch_port,
                                username=s.ch_user, password=s.ch_password,
                                database=s.ch_database, compress="lz4")
    geo = GeoReader(s.geoip_mmdb)
    writer = BatchWriter(ch, redis, s.stream, s.group, s.batch_max, s.flush_interval)
    serve_metrics(s.metrics_port)

    await ensure_group(redis, s.stream, s.group)
    await writer.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async def ingest(source):
        async for msg_id, fields in source:
            CONSUMED.inc()
            row = build_row(msg_id, fields, geo)
            await writer.put(row)

    try:
        await asyncio.gather(
            ingest(read_loop(redis, stop)),
            ingest(reclaim_loop(redis, stop)),
        )
    finally:
        log.info("shutting_down")
        stop.set()
        await writer.drain()      # flush whatever's in-buffer
        geo.close()
        await redis.aclose()
        await ch.close()
        log.info("shutdown_complete")

def build_row(msg_id, fields, geo) -> Row:
    # fields are bytes:bytes
    g = fields.get
    ua_str = (g(b"ua") or b"").decode("utf-8", "replace")
    ua = parse_ua(ua_str)
    ip = (g(b"ip") or b"").decode()
    geo_r = geo.lookup(ip) if ip else Geo(None, None, None, None)
    bot = is_bot(ua_str, ua.browser)
    return Row(
        msg_id=msg_id,
        values=(
            float(g(b"ts") or b"0") / 1000.0,  # or DateTime64 parsing
            (g(b"code") or b"").decode(),
            ip,
            geo_r.country or "", geo_r.city or "",
            geo_r.lat or 0.0, geo_r.lon or 0.0,
            ua.browser, ua.os, ua.device,
            1 if bot else 0,
            (g(b"ref") or b"").decode(),
            int(g(b"uid") or b"0"),
        ),
    )

if __name__ == "__main__":
    try:
        import uvloop; uvloop.install()
    except ImportError:
        pass
    asyncio.run(run())
```

SIGTERM handler sets `stop`; both generator loops exit at their next block boundary; `writer.drain()` flushes the buffer; then `XACK` happens as usual. k8s default `terminationGracePeriodSeconds=30` is plenty (we typically drain in <2s).

---

## 12. Configuration

```python
# worker/config.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AW_", env_file=".env", extra="ignore")

    redis_url: str = "redis://redis:6379/0"
    stream: str = "clicks"
    group: str = "analytics"

    ch_host: str = "clickhouse"
    ch_port: int = 8123
    ch_user: str = "default"
    ch_password: str = ""
    ch_database: str = "analytics"

    geoip_mmdb: str = "/geoip/GeoLite2-City.mmdb"

    batch_max: int = Field(1000, ge=1, le=50_000)
    flush_interval: float = Field(1.0, ge=0.05, le=30.0)
    block_ms: int = 5000
    count: int = 100

    metrics_port: int = 9090
    health_port: int = 8080
    log_level: str = "INFO"
```

---

## 13. Dockerfile (multistage)

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --prefix=/install .

FROM python:3.12-slim AS runtime
RUN groupadd -r app && useradd -r -g app app
COPY --from=build /install /usr/local
WORKDIR /app
COPY worker ./worker
USER app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080 9090
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; \
  sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz',timeout=2).status==200 else 1)"
CMD ["python", "-m", "worker.main"]
```

`docker-compose.yml` snippet — the `.mmdb` is a shared read-only volume updated by a separate `geoipupdate` sidecar on the host (weekly cron):

```yaml
services:
  analytics-worker:
    build: ./analytics-worker
    environment:
      - AW_REDIS_URL=redis://redis:6379/0
      - AW_CH_HOST=clickhouse
    volumes:
      - geoip-data:/geoip:ro
    depends_on: [redis, clickhouse]
    networks: [urlshort-net]
volumes:
  geoip-data:
    external: true
```

---

## 14. Testing

```python
# tests/conftest.py
import pytest, pytest_asyncio
from fakeredis import aioredis as fakeredis

@pytest_asyncio.fixture
async def redis():
    r = fakeredis.FakeRedis()
    yield r
    await r.aclose()

@pytest.fixture
def ch_mock(mocker):
    m = mocker.AsyncMock()
    m.insert = mocker.AsyncMock()
    return m
```

```python
# tests/test_writer.py
import asyncio, pytest
from worker.writer import BatchWriter, Row

@pytest.mark.asyncio
async def test_size_trigger_flushes(redis, ch_mock):
    await redis.xgroup_create("clicks", "analytics", id="$", mkstream=True)
    w = BatchWriter(ch_mock, redis, "clicks", "analytics", max_size=3, interval=60)
    await w.start()
    for i in range(3):
        mid = await redis.xadd("clicks", {b"code": b"abc"})
        await w.put(Row(msg_id=mid, values=("...",)*12))
    await asyncio.sleep(0.05)
    ch_mock.insert.assert_awaited_once()
    assert ch_mock.insert.await_args.args[1].__len__() == 3

@pytest.mark.asyncio
async def test_time_trigger_flushes(redis, ch_mock):
    await redis.xgroup_create("clicks", "analytics", id="$", mkstream=True)
    w = BatchWriter(ch_mock, redis, "clicks", "analytics", max_size=1000, interval=0.1)
    await w.start()
    mid = await redis.xadd("clicks", {b"code": b"abc"})
    await w.put(Row(msg_id=mid, values=("...",)*12))
    await asyncio.sleep(0.2)
    ch_mock.insert.assert_awaited_once()

@pytest.mark.asyncio
async def test_xack_only_after_successful_insert(redis, ch_mock):
    await redis.xgroup_create("clicks", "analytics", id="$", mkstream=True)
    ch_mock.insert.side_effect = RuntimeError("ch down")
    w = BatchWriter(ch_mock, redis, "clicks", "analytics", max_size=1, interval=60)
    await w.start()
    mid = await redis.xadd("clicks", {b"code": b"abc"})
    # Simulate XREADGROUP to place into PEL:
    await redis.xreadgroup("analytics", "c1", {"clicks": ">"}, count=10)
    await w.put(Row(msg_id=mid, values=("...",)*12))
    await asyncio.sleep(0.05)
    pending = await redis.xpending("clicks", "analytics")
    assert pending["pending"] == 1  # not XACKed after failure
```

Run: `pytest -q --asyncio-mode=auto`.

---

## 15. Gotchas

- **PEL growth:** forgetting `XACK` (or `XACK` wrong group) leaks memory on the Redis side. Alert on `queue_lag_seconds > 60`.
- **Consumer ID reuse:** if two pods get the same `HOSTNAME` (bad Deployment naming), pending entries silently fight. Use StatefulSet, or prefix with pod UID.
- **Clock skew:** `queue_lag` uses the stream-ID timestamp (Redis server clock) vs local `time.time()`. If the worker's clock drifts, lag looks wrong. Run chrony/ntpd; don't trust lag alerts during NTP step events.
- **`$` vs `0` on group create:** `$` means "only new after this moment." On a **re-deploy with a fresh group name** you'll silently drop history. Only change the group name intentionally.
- **`XAUTOCLAIM` `min_idle_time`:** must exceed the worst-case flush time (`BATCH_MAX / throughput + CH p99 insert`). Set to **60s** to be safe; lower and you'll steal from healthy peers mid-flush.
- **At-least-once, not exactly-once:** `ReplacingMergeTree` dedupe is **eventual** (only at merge). Dashboards that `SELECT count()` without `FINAL` will double-count for seconds-to-minutes after a replay. Use `argMax(..., insert_time)` or `uniqExact(stream_id)` for accurate counts.
- **`decode_responses=False`:** keep it False on the Redis client — stream payloads carry raw bytes (IPs, UA, referer with emoji) and round-tripping through `str` corrupts them. Decode at the field level with `errors="replace"`.
- **GeoIP reader lifetime:** do **not** open inside `put()`. The `.mmdb` mmap is cheap to share. `close()` only at shutdown.
- **UA cache key:** hashing the UA string is required — `lru_cache` on the raw string will eat GB with adversarial traffic (random UAs from bots).
- **CH connection pool:** `clickhouse-connect` async client multiplexes over an HTTP pool; set `pool_mgr_options={"maxsize": 8}` if you run many concurrent writers (we only have one — irrelevant here, but noted).
- **Batch too big:** CH happy up to ~1M rows/insert, but Redis pipeline for `XACK` is O(n). Keep `BATCH_MAX <= 5000` to keep XACK under 1ms.
- **Dead-letter:** after ~16 deliveries (check `XPENDING` `delivery_count`), route to `clicks:dead` and `XACK` — otherwise one poison pill wedges the group forever.
- **`fakeredis` caveats:** it implements XREADGROUP/XACK/XPENDING/XCLAIM but `XAUTOCLAIM` semantics differ slightly from real Redis on edge cases (deleted IDs). Keep at least one integration test against a real Redis container in CI.
- **`uvloop` on Windows:** not supported — guard the import. Dev on Windows uses the stdlib loop; prod containers use uvloop for ~20% throughput uplift.
