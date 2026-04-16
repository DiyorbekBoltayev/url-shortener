# admin-panel

URL Shortener admin SPA — Angular 19 (standalone + signals + new control flow) + PrimeNG 19 (Aura) + Tailwind CSS 3.4.

Served by nginx in production on container port `80`. The root reverse proxy in `infrastructure/` forwards `/`, `/dashboard/*`, and friends to this container over the shared `url-shortener-net` network.

## Stack

- Angular 19.2.x (esbuild builder, `@angular/build:application`)
- PrimeNG 19 + `@primeng/themes` (Aura preset)
- Tailwind CSS 3.4 (with PostCSS + Autoprefixer)
- `@ngrx/signals` — thin SignalStore pattern, no reducer/action boilerplate
- `ng-apexcharts` + `apexcharts` for analytics charts (`@defer (on viewport)`)
- `qrcode` for client-side QR rendering on the link-detail page
- TypeScript 5.6, strict mode + strict templates
- Karma + Jasmine for unit tests (Vitest not yet default in 19.x)
- Node 20-alpine → Nginx 1.25-alpine (multistage Dockerfile)

## Quick start

```bash
make install        # npm ci
make dev            # ng serve --proxy-config proxy.conf.json on :4200
make build          # production build into dist/admin-panel/browser
make test-ci        # ChromeHeadless one-shot
make up             # docker compose up (joins url-shortener-net)
```

## Local development modes

The dev server proxies `/api/*` to a backend. Two proxy configs are shipped — pick based on what you're running locally.

### Mode A — API only (default, recommended for frontend work)

Run just the infra stack (Postgres/Redis) and `api-service` standalone on host port `8000`, then:

```bash
npm run dev         # ng serve --proxy-config proxy.conf.json → http://localhost:8000
```

`proxy.conf.json` targets `http://localhost:8000` (api-service direct). This is the fastest loop for frontend dev: you don't need the root nginx, short-url-service, or analytics-consumer running.

### Mode B — full stack (through root nginx)

Bring up every compose file (infrastructure + api-service + short-url-service + analytics-consumer + admin-panel — see repo root `README.md`), then:

```bash
npm run dev:nginx   # ng serve --proxy-config proxy.conf.nginx.json → http://localhost:80
```

`proxy.conf.nginx.json` targets `http://localhost:80` (the root infra nginx on the host), so `/api/*` is routed exactly as it will be in production. Use this when verifying CORS, rate-limit headers, or routing changes that live in the root nginx config.

> Tip: both modes assume `environment.ts` keeps `apiBaseUrl: '/api'` — only the proxy target changes.

## Pages (all lazy-loaded)

| Route | Guard | Purpose |
|---|---|---|
| `/` | public | Landing + "shorten your URL" form (anonymous) |
| `/login`, `/register` | public | Auth |
| `/dashboard` | `authMatchGuard` | KPIs + timeseries |
| `/dashboard/links` | `authMatchGuard` | PrimeNG `p-table`, server-side paging (offset/limit) |
| `/dashboard/links/new` | `authMatchGuard` | Create form (reactive, async slug-uniqueness) |
| `/dashboard/links/:id` | `authMatchGuard` | Detail + analytics + QR download |
| `/dashboard/domains` | `authMatchGuard` | Custom domains |
| `/dashboard/api-keys` | `authMatchGuard` | Tokens (shown once) |
| `/dashboard/webhooks` | `authMatchGuard` | Endpoint CRUD |
| `/dashboard/settings` | `authMatchGuard` | Profile |

Unauthenticated access to `/` shows the public landing — we do **not** redirect anonymous users to `/login` so the SPA can function as a public shortener too.

## Auth flow

- Backend issues `access_token` (15 min) + `refresh_token` (7 days) per `research/05-HLA` §7.
- **Access token** — kept in an in-memory `signal<string | null>` on `AuthService`. Never written to storage. Lost on reload (triggers silent refresh via stored refresh token on bootstrap).
- **Refresh token** — stored in `localStorage` under key `rt`. Ideal would be an `httpOnly; Secure; SameSite=Strict` cookie set by the backend, but that requires a backend change; localStorage is the documented tradeoff for v1.
  - **Tradeoff**: localStorage is readable by any in-origin JS, so any XSS compromise steals the refresh token (session persistence across browser restarts is the upside).
  - **Migration path**: when the API starts issuing cookies on `/auth/login` and `/auth/refresh`, delete `token.storage.ts` refresh read/write and remove the `refresh_token` field from request bodies — the interceptor already uses `withCredentials: true`.
- On any `401` (except on `/auth/refresh`), `auth.interceptor.ts` calls `AuthService.refresh()` single-flight and retries the original request. On refresh failure, `AuthService.logout()` + redirect to `/login`.

## Folder layout

```
src/app/
  app.config.ts            # standalone providers (router, http, interceptors, PrimeNG)
  app.routes.ts            # lazy routes
  app.component.ts
  core/
    api/                   # typed HttpClient wrappers per domain
    auth/                  # AuthService (signals), guard (CanMatchFn), interceptor
    layout/                # DashboardShellComponent (sidebar + topbar)
    models/
  shared/
    components/            # copy-button, stat-card, empty-state
    pipes/
  features/
    landing/
    auth/                  # login + register
    dashboard/             # overview
    links/                 # list + create + detail + LinksStore
    domains/
    api-keys/
    webhooks/
    settings/
```

## Build output

Angular 19 (esbuild) emits:

```
dist/admin-panel/browser/
  index.html
  main-*.js
  polyfills-*.js
  styles-*.css
  chunk-*.js   (lazy feature chunks)
```

Nginx copy path must end with `/browser` (see `Dockerfile`).

## Configuration

Build-time — `src/environments/environment.ts` (replaced at prod build by `environment.prod.ts`):

```ts
export const environment = {
  production: false,
  apiBaseUrl: '/api',
  publicShortHost: 'http://localhost',
  appName: 'URL Shortener Admin'
};
```

Runtime — optionally mount `/assets/config.json` into nginx for hotfix without rebuild (see `nginx.conf` — that path is served no-cache).

## Integration Contract compliance

- Internal port `80` (not published). ✅
- Upstream nginx routes `/`, `/dashboard/*` here. ✅
- `API_BASE_URL=/api` — every HTTP call is same-origin via the root proxy. ✅
- Healthcheck `wget -q --spider http://localhost/`. ✅
- JSON response envelope `{ success, data, meta }` handled by `ApiService` / `api.response.model.ts`. ✅
- Paging is **offset/limit** (`page` + `per_page`) matching HLA §7. ✅

## Known follow-ups

- Unit test coverage — scaffolding only; add coverage for `AuthService.refresh` single-flight, interceptor 401 path, LinksStore filters.
- Accessibility audit — PrimeNG components are ARIA-labeled but the custom layout (sidebar, topbar) needs keyboard-trap + focus-visible review.
- E2E — Playwright recommended; not in scope for v1.
- SSR/hydration — kept off; SPA-only is sufficient for an admin panel.

## License

MIT — see `LICENSE`.
