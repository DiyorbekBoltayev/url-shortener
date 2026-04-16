# RV5 — admin-panel review

**Auditor:** RV5
**Date:** 2026-04-14
**Target:** `C:\Users\User\Desktop\work\url-shortener\admin-panel\`
**Scope:** Angular 19 SPA built by C5 — against INTEGRATION_CONTRACT.md, HLA 2.4 + Angular 19 override, and `research/tech/angular19-admin.md`.

## Verdict

**PASS (ship-ready) with 1 pre-ship fix and a handful of nits.**

The panel is cleanly built on the Angular 19 stack the user mandated: standalone bootstrap, functional interceptors + guards, signal-based stores, lazy routes end-to-end, new control-flow templating. No blocker-class defects. One pre-ship issue: the dev-only `proxy.conf.json` points at `http://localhost:80` which is the prod nginx host, not the dev redirect/api — fix before a contributor first runs `npm start` against the local compose stack.

## BLOCKER checklist

| # | Check | Result | Evidence |
|---|---|---|---|
| B1 | Angular >= 19 | PASS | `package.json` deps pinned `^19.2.0` across `@angular/*`, CLI, build, cdk; `@ngrx/signals ^19.0.0`; `primeng ^19`. |
| B2 | No React/Next/Vue imports | PASS | grep for `react\|vue\|next/` → only literal text ("ReactiveFormsModule", "react" substring inside `reactively`) — no framework imports. |
| B3 | Standalone bootstrap via `bootstrapApplication` | PASS | `src/main.ts:5` calls `bootstrapApplication(AppComponent, appConfig)`. No `@NgModule`, no `bootstrapModule`, no `AppModule`. `AppComponent` is `standalone: true`. |
| B4 | No `*ngIf` / `*ngFor` / `*ngSwitch` | PASS | Grep across `src/` — zero occurrences. New control-flow `@if`/`@for` used in 14 files, 47 total occurrences. |
| B5 | Auth interceptor functional (`HttpInterceptorFn`) | PASS | `core/auth/auth.interceptor.ts:20` exports `HttpInterceptorFn`. Same for `api-base.interceptor.ts`, `error.interceptor.ts`. No class-based `HttpInterceptor`. |
| B6 | Guards functional (`CanMatchFn`/`CanActivateFn`) | PASS | `core/auth/auth.guard.ts` exports `authGuard: CanMatchFn` and `guestGuard: CanMatchFn`. Used via `canMatch: [authGuard]` (no legacy `canActivate: [Class]`). |
| B7 | Refresh flow: no infinite-loop on repeated 401, no concurrent refresh calls | PASS | `AuthService.refresh()` uses an `isRefreshing` flag + `BehaviorSubject` lock so concurrent callers subscribe to the same in-flight refresh. Interceptor excludes `/auth/refresh` itself from re-entry (`ANON_PATHS`). On refresh failure the interceptor calls `auth.logout()` and propagates the error rather than re-retrying → no infinite loop. |
| B8 | `provideHttpClient` wiring | PASS | `app.config.ts:18` `provideHttpClient(withFetch(), withInterceptors([apiBase, auth, error]))`. No legacy `HttpClientModule`. Interceptor order is correct: api-base rewrites URL first, then auth attaches token, then error surfaces toasts. |
| B9 | Routes lazy | PASS | Every route in `app.routes.ts`, `auth.routes.ts`, `dashboard.routes.ts` uses `loadComponent` / `loadChildren`. Dashboard fans out to six lazy feature chunks (links, domains, api-keys, webhooks, settings + overview). `canMatch` guards fire **before** the chunk downloads — correct. |
| B10 | No single main-chunk dump of feature code | PASS | Feature components only referenced via dynamic `import()`. |
| B11 | API URL from env (default `/api`) | PASS | `environment.ts` + `environment.prod.ts` both export `apiBaseUrl: '/api'`. `api-base.interceptor.ts` prepends it to every relative URL. `AuthService` also references `environment.apiBaseUrl` explicitly. No hardcoded host in API calls. |
| B12 | No XSS via `innerHTML` with unsanitized user data | PASS | Grep for `innerHTML` / `bypassSecurityTrust` → zero matches. |
| B13 | CSRF cookie handling if needed | N/A | Backend uses bearer-token auth (access in memory + refresh body field). No cookie-session auth expected per contract, so no CSRF token plumbing required. The localStorage-refresh-token tradeoff is called out in AuthService docblock (see B20). |
| B14 | Dockerfile: builder not `:latest`, correct esbuild output, SPA fallback, gzip | PASS | `FROM node:20-alpine` (pinned, not latest). Runtime `nginx:1.25-alpine`. Copies `dist/admin-panel/browser` (correct esbuild path). `nginx.conf` has `try_files $uri $uri/ /index.html;` SPA fallback, `gzip on` with sensible types, long-cache for hashed assets, `no-store` on `/index.html`. Security headers present. |
| B15 | `docker-compose.yml` with external network | PASS | `docker-compose.yml` declares `networks: url-shortener-net: external: true name: url-shortener-net` exactly per contract §1. No host port binding — correctly proxied by upstream root nginx (contract §2 says admin-panel is reached via nginx only). Healthcheck + restart policy present. |
| B16 | `angular.json` budget config | PASS | Production config sets `initial` budget `1mb warn / 1.5mb error` and `anyComponentStyle 20kb/40kb`. |
| B17 | No stray `console.log` in prod code | PASS | Grep for `console\.(log\|warn\|debug\|error)` → only `src/main.ts:7` `console.error('[bootstrap]', …)` inside the `bootstrapApplication().catch()` fallback. That is the single documented bootstrap-failure escape hatch (with an eslint-disable comment acknowledging the exception) and is standard practice. Not a blocker. |
| B18 | localStorage refresh-token tradeoff documented | PASS | `auth.service.ts` lines 16-26 spell out the tradeoff and the drop-in swap path to `httpOnly; Secure; SameSite=Strict` cookies. |

All 18 blocker checks pass.

## Pre-ship fix (must-fix, not blocker-severity)

**F1. `proxy.conf.json` target.** Current value `http://localhost:80` implies a root nginx running on the host during `ng serve`. That works only when the full `infrastructure/` compose is up on the host. For a dev experience that actually exercises the interceptors, it should either:
- stay at `http://localhost` (port 80 is default) — document the requirement in README, **or**
- point directly at `http://localhost:8000` (api-service) when contributors want to bypass the reverse proxy.
Current value will silently 404 every API call the first time a new contributor runs `npm start` without the infra stack. Low effort: add a one-line README note or switch the target. Not blocker because production serving path is unaffected (nginx in container serves static only; `/api` is routed by root nginx).

## NIT checklist

| # | Nit | Status | Notes |
|---|---|---|---|
| N1 | Dark mode toggle | PARTIAL | PrimeNG theme is wired with `darkModeSelector: '.dark'` in `app.config.ts:28` — infrastructure is there, but no UI toggle component was located in `shared/components/` or `layout/`. User can only flip it via devtools class. Ship-acceptable but worth a follow-up. |
| N2 | Loading states on long ops | PASS | `LinksStore` exposes `loading()` signal; `list.component.ts` binds it to `[loading]="store.loading()"` on `p-table`. Error interceptor surfaces toasts globally. Good. |
| N3 | Error-boundary equivalent | PARTIAL | Global `errorInterceptor` handles network/5xx/403/429 via toast. No `ErrorHandler` provider for uncaught template/runtime errors (Angular defaults to console). Consider a custom `ErrorHandler` that routes to Sentry or a toast for v1.1. |
| N4 | Tests | PARTIAL | Only `auth.service.spec.ts` found (67 lines, covers login/logout/token persistence). No component tests, no store tests, no interceptor tests. Karma+Jasmine is wired in `angular.json` and `package.json` has `test:ci`. Acceptable for a v1 admin panel that isn't mission-critical but should be tracked. |
| N5 | a11y aria on custom components | PARTIAL | `aria-label` present on the delete button in `list.component.ts:102`. `empty-state` and `stat-card` use semantic HTML. Not exhaustively audited — no obvious gaps in the files sampled. |

## Positive findings worth calling out

- **Signal-first state.** `LinksStore` (`features/links/links.store.ts`) is a clean signal-only store — no NgRx Redux boilerplate, uses `signal`/`computed`/`update`, async methods with `firstValueFrom`. Matches research doc recommendation. `@ngrx/signals` is pulled in but not over-used — good restraint.
- **Single-flight refresh.** The `BehaviorSubject`-based lock in `AuthService.refresh()` correctly serialises concurrent 401s; interceptor excludes `/auth/refresh` and other anonymous paths from the retry path, preventing recursion.
- **`canMatch` (not `canActivate`) on lazy routes.** Unauthenticated users never download the dashboard bundle — this is the correct Angular-19 pattern and matches the comment in `auth.guard.ts`.
- **tsconfig strictness.** `strict`, `noImplicitOverride`, `noPropertyAccessFromIndexSignature`, `noImplicitReturns`, `strictTemplates`, `strictInjectionParameters` all on.
- **`OnPush` default via schematics** in `angular.json` — every new component will be change-detection-lean by default.
- **No absolute API hostnames** anywhere in source. The two `http://`/`https://` occurrences in `src/` are either `publicShortHost` in dev env, or `placeholder="https://…"` form-hint strings, or the literal regex in `api-base.interceptor.ts`. All legitimate.

## Files read

- `C:\Users\User\Desktop\work\url-shortener\admin-panel\package.json`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\angular.json`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\tsconfig.json`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\Dockerfile`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\docker-compose.yml`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\nginx.conf`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\proxy.conf.json`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\main.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\environments\environment.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\environments\environment.prod.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\app.config.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\app.routes.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\app.component.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\app.component.html`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\auth\auth.service.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\auth\auth.service.spec.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\auth\auth.interceptor.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\auth\auth.guard.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\auth\api-base.interceptor.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\auth\error.interceptor.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\auth\auth.routes.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\dashboard\dashboard.routes.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\links\links.store.ts`
- `C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\links\list.component.ts`

## Recommendation

Ship. Before merge: apply **F1** (document or fix `proxy.conf.json` target). After merge, track the nits (dark-mode toggle, `ErrorHandler`, broader test coverage) as v1.1 follow-ups.
