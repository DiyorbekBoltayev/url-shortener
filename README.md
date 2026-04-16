# URL Shortener — Multi-Repo Monorepo Workspace

A production-grade, bit.ly-style URL shortener built as **five independent
repositories** that cooperate through a shared Docker network and a strict
integration contract. Hybrid stack: **Go** for the hot redirect path,
**FastAPI** for the admin API, **Python asyncio** for the analytics pipeline,
and **Angular 19** for the dashboard UI.

This top-level directory is **not itself a git repo** — it is the orchestration
layer. Each sub-directory is a self-contained repo that will be pushed to its
own git remote (`git init && git remote add origin ...` per folder).

---

## Architecture

```
                        ┌──────────────────────────────────┐
                        │         USERS / CLIENTS          │
                        │   (browser, mobile, API client)  │
                        └──────────────┬───────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────────┐
                        │              NGINX               │
                        │        (reverse proxy, TLS)      │
                        │                                  │
                        │  /{1-10 alnum}  → redirect-service│
                        │  /api/*         → api-service     │
                        │  /dashboard/*   → admin-panel     │
                        │  /, /docs, ...  → admin-panel     │
                        └─────┬────────────────┬───────────┘
                              │                │
                ┌─────────────▼──┐    ┌───────▼──────────────┐
                │                │    │                      │
                │  REDIRECT-SVC  │    │    API-SERVICE       │
                │     (Go)       │    │    (FastAPI)         │
                │                │    │                      │
                │ GET /{code}    │    │ URLs CRUD, Auth,     │
                │ GET /health    │    │ Analytics API,       │
                │ Redis lookup   │    │ Domains, QR, Webhooks│
                │ 302 + XADD     │    │ Rate limiting        │
                └──┬─────────┬───┘    └───┬──────────┬───────┘
                   │         │            │          │
          ┌────────▼──┐  ┌──▼──────┐  ┌──▼──────┐  ┌▼──────────┐
          │ REDIS     │  │ REDIS   │  │POSTGRES │  │CLICKHOUSE │
          │ CACHE     │  │ STREAMS │  │ 17      │  │ 24        │
          │ :6379 db0 │  │ :6380   │  │ URLs,   │  │ raw clicks│
          │ url:<c>   │  │ clicks  │  │ Users,  │  │ aggregates│
          └───────────┘  └────┬────┘  │ Domains │  └─────▲─────┘
                              │       │ Keys    │        │
                              ▼       └─────────┘        │
                       ┌──────────────────┐              │
                       │ ANALYTICS-WORKER │──────────────┘
                       │    (Python)      │
                       │                  │
                       │ Redis Streams →  │
                       │ GeoIP + UA enrich│
                       │ → batch insert   │
                       └──────────────────┘

                             ┌──────────────┐
                             │ ADMIN-PANEL  │ (Angular 19 SPA, served by nginx)
                             └──────────────┘
```

Shared services run from **`infrastructure/`**: Postgres, Redis×2,
ClickHouse, MinIO, Nginx, Prometheus, Grafana, geoipupdate.
All 9 containers attach to the external Docker network
**`url-shortener-net`** (bridge, subnet `172.28.0.0/16`).

---

## The five repos

| # | Repo folder          | Purpose                                        | Stack                                  | Port(s) (internal)        |
|---|----------------------|------------------------------------------------|----------------------------------------|---------------------------|
| 1 | `infrastructure/`    | Shared data stores + nginx + monitoring        | docker-compose, Postgres 17, Redis 7.2×2, ClickHouse 24, MinIO, Nginx 1.25, Prometheus, Grafana | 80/443 (nginx), 5432, 6379, 6380, 8123/9000, 9002/9001, 9090, 3001 |
| 2 | `redirect-service/`  | `GET /{code}` hot path, <5 ms p99 redirect     | Go 1.22, Fiber v2, go-redis v9, pgx v5, zerolog | 8080 (internal only)      |
| 3 | `api-service/`       | Admin CRUD + auth + analytics read API         | Python 3.12, FastAPI 0.115, SQLAlchemy 2.0 async, Alembic, PyJWT, pwdlib | 8000 (internal only)      |
| 4 | `analytics-worker/`  | Redis Streams consumer → GeoIP/UA → ClickHouse | Python 3.12, asyncio, redis-py, clickhouse-connect, geoip2, ua-parser | 9091 (metrics), 9092 (health) |
| 5 | `admin-panel/`       | Dashboard SPA (links, domains, analytics, billing) | Angular 19, standalone + signals, PrimeNG 19, Tailwind 3, nginx-alpine | 80 (internal only)        |

Only **nginx** exposes public host ports (80/443). Everything else is
reachable inside the shared network by DNS name (`postgres`, `redis-cache`,
`redis-app`, `clickhouse`, `api-service`, `redirect-service`, ...).

The full integration contract lives in
[`INTEGRATION_CONTRACT.md`](./INTEGRATION_CONTRACT.md) — read it before
changing any env-var name, stream name, or port.

---

## Quick start

### Prerequisites

- **Docker 24+** with the Docker Compose v2 plugin (`docker compose`, not `docker-compose`)
- **GNU Make** (pre-installed on Linux/macOS; on Windows use Git Bash or WSL2)
- Ports **80, 443, 3001, 5432, 6379, 6380, 8123, 9000, 9001, 9002, 9090** free
- For local (non-Docker) development of individual services:
  - **Go 1.22+** — `redirect-service`
  - **Python 3.12** + **uv** (or pip) — `api-service`, `analytics-worker`
  - **Node 20+** + **npm** — `admin-panel`

### One-liner boot

```bash
cp infrastructure/.env.example infrastructure/.env   # repeat per service if you want overrides
make up
```

This will:

1. Create the shared Docker network `url-shortener-net` (idempotent).
2. Start the `infrastructure/` compose (DBs, nginx, monitoring).
3. Wait 10 s for healthchecks to settle.
4. Start `redirect-service`, `api-service`, `analytics-worker`, `admin-panel`
   in that order.

When it completes, open:

- <http://localhost> — admin panel (sign up, create a link)
- <http://localhost/api/docs> — FastAPI Swagger UI
- <http://localhost:3001> — Grafana (admin / admin by default)
- <http://localhost:9090> — Prometheus

Check everything is green:

```bash
make health
make ps
make logs     # ctrl-c to stop tailing
```

Tear down (network and volumes are preserved):

```bash
make down
```

---

## Root Makefile targets

Run `make help` for the live list.

| Target        | What it does                                                            |
|---------------|-------------------------------------------------------------------------|
| `net`         | Create `url-shortener-net` if missing                                   |
| `up-infra`    | `make -C infrastructure up`                                             |
| `up-apps`     | Start the 4 app composes in dependency order                            |
| `up`          | Network + infra + sleep 10 + apps                                       |
| `down-apps`   | Stop the 4 app composes (reverse order)                                 |
| `down-infra`  | Stop infrastructure                                                     |
| `down`        | Stop apps then infra (keeps volumes + network)                          |
| `logs`        | Tail merged logs from all 9 services                                    |
| `ps`          | `docker ps --filter network=url-shortener-net`                          |
| `health`      | Curl each service's health endpoint                                     |
| `build`       | Build every locally-built image                                         |
| `clean`       | Prune dangling images + unused anonymous volumes                        |
| `verify`      | Grep every compose to confirm it references `url-shortener-net`         |

---

## Per-service development workflow

Each sub-repo has its own `README.md` and `Makefile`. Typical iteration
targets the **one** service you're working on while keeping the rest under
Docker.

| Service              | Dev command (from inside the folder)          | README                                                |
|----------------------|-----------------------------------------------|-------------------------------------------------------|
| `infrastructure/`    | `make up` / `make logs` / `make psql`         | [infrastructure/README.md](./infrastructure/README.md)|
| `redirect-service/`  | `go mod tidy && make run` (requires Go)       | [redirect-service/README.md](./redirect-service/README.md)|
| `api-service/`       | `uv sync && make dev`                         | [api-service/README.md](./api-service/README.md)      |
| `analytics-worker/`  | `uv sync && make run`                         | [analytics-worker/README.md](./analytics-worker/README.md)|
| `admin-panel/`       | `npm ci && npm start` (proxies to api-service)| [admin-panel/README.md](./admin-panel/README.md)      |

A typical "work on the API only" loop:

```bash
make up-infra                       # start DBs + nginx
cd api-service && make dev          # hot-reload local uvicorn on :8000
```

---

## Testing

Tests live inside each repo (`tests/` folder, `*_test.go`, `.spec.ts`).
Run them from the service directory, **not** from the root:

```bash
cd redirect-service  && make test        # go test ./... -race
cd api-service       && make test        # pytest -q
cd analytics-worker  && make test        # pytest -q
cd admin-panel       && make test-ci     # headless Karma
```

There is no cross-repo integration test harness at the root yet; the
closest thing is `make up && make health`, which brings the entire stack
up and asserts every `/health` endpoint returns 200.

---

---

## Troubleshooting

### "network url-shortener-net not found"
Run `make net` (or `make up` which does it for you). To inspect:
```bash
docker network inspect url-shortener-net
```

### Port conflict (e.g. :80, :5432, :3001)
Something else on your host already holds the port. Either stop the
offender or edit `infrastructure/.env` to remap `*_HOST_PORT` variables
(e.g. `POSTGRES_HOST_PORT=5433`). The internal container ports are fixed
by the integration contract.

### Inspect a volume
```bash
docker volume ls | grep urlshortener
docker volume inspect urlshortener-postgres-data
docker run --rm -v urlshortener-postgres-data:/d alpine ls -la /d
```

### Full reset (destroys data!)
```bash
make down
docker compose -f infrastructure/docker-compose.yml down -v
docker network rm url-shortener-net
```

### Service not reachable from another service
Confirm both containers are on `url-shortener-net`:
```bash
make ps
```
Both names must appear. If only one does, that service's compose file is
mis-configured (missing `networks: [url-shortener-net]` or the external
declaration).

### redirect-service fails to compile
Go is **not** installed in the dev container used to build these files.
You must run `go mod tidy` on your machine before the first docker build
so `go.sum` gets generated.

---

## Contributing

Contract changes (env names, ports, stream names, cache keys, volume
names) must be coordinated **across all affected repos simultaneously**.
Update `INTEGRATION_CONTRACT.md` first, then the service repos that
consume that piece of the contract, then re-run `make up && make health`.

Follow the existing code style in each repo:
- Go: `gofmt`, `golangci-lint`
- Python: `ruff`, `mypy` (where configured)
- TypeScript: `eslint`, `prettier`

---

## License

MIT — see the `LICENSE` file in each sub-repo.
