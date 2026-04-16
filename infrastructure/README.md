# URL Shortener — Infrastructure

Shared infrastructure stack for the URL Shortener multi-repo project:
PostgreSQL, Redis (cache + app), ClickHouse, MinIO, Nginx, Prometheus,
Grafana, and the MaxMind GeoIP updater.

All four application repos (`redirect-service`, `api-service`,
`analytics-worker`, `admin-panel`) attach to the same external Docker
network created here.

---

## Quick start

```bash
cp .env.example .env           # adjust secrets
make net                       # create url-shortener-net (once)
make up                        # start the stack (dev)
make ps                        # verify
make health                    # probe each service
```

Prod:

```bash
make up-prod                   # applies docker-compose.prod.yml overrides
```

---

## Service URLs (dev)

| Service       | URL                                         | Notes                                   |
| ------------- | ------------------------------------------- | --------------------------------------- |
| Nginx         | http://localhost                            | Gateway for `/`, `/api/`, `/{code}`     |
| Prometheus    | http://localhost:9090                       | Metrics UI                              |
| Grafana       | http://localhost:3001                       | `admin` / `admin` (change via `.env`)   |
| MinIO console | http://localhost:9001                       | `minioadmin` / `.env`                   |
| MinIO S3 API  | http://localhost:9002                       | Internal services use `minio:9000`      |
| ClickHouse    | http://localhost:8123 / `clickhouse:9000`   | HTTP / native                           |
| Postgres      | `postgres://localhost:5432/urlshortener`    | Only dev exposes the port               |
| Redis cache   | `redis://localhost:6379/0`                  | Port 6379                               |
| Redis app     | `redis://localhost:6380/0`                  | Port 6380 (streams + rate limit)        |

---

## Plugging in the 4 app repos

Each app repo's `docker-compose.yml` must declare:

```yaml
networks:
  url-shortener-net:
    external: true
    name: url-shortener-net

services:
  <app-name>:
    networks:
      - url-shortener-net
```

App service names (DNS-resolvable inside the network): `redirect-service`,
`api-service`, `analytics-worker`, `admin-panel`. Nginx proxies to them by
those names via Docker's embedded DNS (`127.0.0.11`) with
`resolver valid=10s`, so app restarts don't break routing.

`geoip-data` volume is read by `redirect-service` and `analytics-worker`.
Declare it in their compose as:

```yaml
volumes:
  urlshortener-geoip-data:
    external: true
    name: urlshortener-geoip-data

services:
  <app-name>:
    volumes:
      - urlshortener-geoip-data:/data:ro
```

Bootstrap order (handled by the root-level orchestrator Makefile):

1. `make net` (this repo) once per host.
2. `make up` (this repo) — wait for healthchecks.
3. `cd redirect-service && docker compose up -d`
4. `cd api-service && docker compose up -d`
5. `cd analytics-worker && docker compose up -d`
6. `cd admin-panel && docker compose up -d`

---

## Troubleshooting

**`Error response from daemon: network with name url-shortener-net already exists`**
Harmless — `make net` is idempotent. If the subnet conflicts:
`docker network rm url-shortener-net && make net`.

**`Bind for 0.0.0.0:5432 failed: port is already allocated`**
Another Postgres (or previous run) is on the host port. Either stop it or
override: `POSTGRES_HOST_PORT=5433 make up`. Production compose removes
these bindings entirely.

**Nginx returns 502 for `/api/` or short codes**
The app container isn't up yet, or it crashed. Nginx's
`resolver 127.0.0.11 valid=10s` re-resolves within 10s after the app
restarts — no nginx reload needed. Check `docker compose logs
redirect-service` in that repo.

**ClickHouse init.sql didn't run**
The init script only runs on a *fresh* volume. Force re-run with
`make ch-init`.

**ClickHouse access management (RBAC) is disabled by default**
`CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT` is set to `"0"` in
`docker-compose.yml` so that an empty `CLICKHOUSE_PASSWORD` in dev does not
grant unauthenticated superuser over the shared Docker network. If you need
RBAC (users, roles, grants), set a strong `CLICKHOUSE_PASSWORD` in `.env`
first, THEN flip the env var to `"1"`. Never enable it with an empty
password.

**`geoip-updater` keeps restarting**
Missing `GEOIP_ACCOUNT_ID` / `GEOIP_LICENSE_KEY`. Register at
maxmind.com (free GeoLite2 tier) and fill them in `.env`. Until then the
redirect service falls back to country lookup from headers.

**Grafana dashboards empty**
Prometheus hasn't discovered the app targets yet — they only come up when
their own repos are started. Check `http://localhost:9090/targets`.

---

## File layout

```
infrastructure/
  docker-compose.yml               # core stack
  docker-compose.prod.yml          # prod overrides (merge file)
  Makefile                         # net/up/down/logs/psql/...
  .env.example
  .gitignore
  .dockerignore
  LICENSE
  README.md
  db/
    init.sql                       # Postgres schema
  clickhouse/
    init.sql                       # ClickHouse schema + MVs
  nginx/
    nginx.conf                     # reverse proxy config
    conf.d/.gitkeep                # extra vhosts
  monitoring/
    prometheus.yml
    grafana/
      provisioning/datasources/prometheus.yml
      provisioning/dashboards/default.yml
      dashboards/url-shortener.json
```
