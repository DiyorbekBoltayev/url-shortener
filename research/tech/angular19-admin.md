# Angular 19 Admin Panel — Production Reference

Target: the URL-shortener admin SPA.
Angular 19.x (released Nov 2024) is mandatory — this supersedes the HLA that mentioned Next.js. React is **not** an option here.

---

## 1. Pinned versions (`package.json`)

Angular 19 ships esbuild as default builder, standalone-by-default, new control flow (`@if / @for / @switch`), signals, `inject()`, functional interceptors and guards.

```json
{
  "name": "shrtnr-admin",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "ng serve --host 0.0.0.0 --port 4200",
    "build": "ng build --configuration production",
    "build:staging": "ng build --configuration staging",
    "test": "ng test",
    "test:ci": "ng test --watch=false --browsers=ChromeHeadless",
    "lint": "ng lint"
  },
  "dependencies": {
    "@angular/animations": "^19.2.0",
    "@angular/cdk": "^19.2.0",
    "@angular/common": "^19.2.0",
    "@angular/compiler": "^19.2.0",
    "@angular/core": "^19.2.0",
    "@angular/forms": "^19.2.0",
    "@angular/localize": "^19.2.0",
    "@angular/platform-browser": "^19.2.0",
    "@angular/platform-browser-dynamic": "^19.2.0",
    "@angular/router": "^19.2.0",
    "@ngrx/signals": "^19.0.0",
    "primeng": "^19.0.0",
    "primeicons": "^7.0.0",
    "@primeng/themes": "^19.0.0",
    "ng-apexcharts": "^1.12.0",
    "apexcharts": "^3.54.0",
    "rxjs": "~7.8.0",
    "zone.js": "~0.15.0"
  },
  "devDependencies": {
    "@angular-devkit/build-angular": "^19.2.0",
    "@angular/cli": "^19.2.0",
    "@angular/compiler-cli": "^19.2.0",
    "@types/jasmine": "~5.1.0",
    "jasmine-core": "~5.2.0",
    "karma": "~6.4.0",
    "karma-chrome-launcher": "~3.2.0",
    "karma-coverage": "~2.2.0",
    "karma-jasmine": "~5.1.0",
    "karma-jasmine-html-reporter": "~2.1.0",
    "tailwindcss": "^3.4.0",
    "typescript": "~5.6.0"
  }
}
```

**Testing**: Angular 19.x still ships Karma+Jasmine as the stable default. Vitest runner is available behind the `refactor-jasmine-vitest` schematic (becomes default in later 19.x minors / Angular 20). For v1 stay on Karma+Jasmine — revisit on the v20 upgrade.

---

## 2. Project layout

Feature-folder, standalone everywhere, no NgModules.

```
admin/
├─ angular.json
├─ package.json
├─ Dockerfile
├─ nginx.conf
└─ src/
   ├─ main.ts
   ├─ environments/{environment.ts, environment.staging.ts, environment.prod.ts}
   └─ app/
      ├─ app.config.ts          # providers, router, interceptors
      ├─ app.routes.ts
      ├─ app.component.ts
      ├─ core/                  # singletons
      │  ├─ auth/{auth.service.ts, auth.store.ts, auth.guard.ts, token.storage.ts}
      │  ├─ http/{auth.interceptor.ts, error.interceptor.ts, api-base.interceptor.ts}
      │  └─ config/app-config.service.ts
      ├─ shared/{ui, pipes, directives, models}
      └─ features/
         ├─ auth/{login.page.ts, register.page.ts, auth.routes.ts}
         ├─ dashboard/{dashboard-shell.component.ts, overview.page.ts, dashboard.routes.ts}
         ├─ links/{links-list.page.ts, link-create.dialog.ts, link-detail.page.ts,
         │         links.store.ts, links.api.ts, links.routes.ts}
         ├─ domains/{domains-list.page.ts, domains.store.ts, domains.api.ts, domains.routes.ts}
         ├─ api-keys/{api-keys.page.ts, api-keys.store.ts, api-keys.api.ts, api-keys.routes.ts}
         ├─ webhooks/{webhooks.page.ts, webhooks.store.ts, webhooks.api.ts, webhooks.routes.ts}
         └─ settings/{settings.page.ts, settings.routes.ts}
```

Rule: `features/*` may import from `core` and `shared`, never from another feature. Cross-feature data flows through `core` services or signal stores.

---

## 3. UI library — **PrimeNG 19 + Tailwind CSS**

**Choice: PrimeNG 19** as the component library, Tailwind for layout/utilities, PrimeIcons for icons.

Why:

- **Coverage**: 90+ components including a production-grade `p-table` with virtual scroll, server paging, resizable/reorderable columns, global/column filters, CSV export — exactly what a links/keys/webhooks admin demands. Angular Material's `mat-table` needs substantial glue for any of those.
- **Admin-dashboard fit**: PrimeNG publishes Sakai-NG (free) and Apollo (premium) Angular 19 starters pre-wired for standalone + signals; we crib the shell layout.
- **Theming**: PrimeNG 19's new `@primeng/themes` design tokens compose cleanly with Tailwind utilities, without the CSS-var fighting Material imposes.
- **vs ng-zorro-antd**: Ant Design is polished but opinionated and harder to rebrand.
- **vs Angular Material**: thin on advanced data components; strict Material Design constrains branding.
- **vs spartan/ui**: great but too much DIY for v1.

Import pattern: per-component standalone imports, e.g. `import { TableModule } from 'primeng/table'`.

---

## 4. Standalone bootstrap

`src/main.ts`:

```ts
import { bootstrapApplication } from '@angular/platform-browser';
import { AppComponent } from './app/app.component';
import { appConfig } from './app/app.config';

bootstrapApplication(AppComponent, appConfig).catch((err) => console.error('[bootstrap]', err));
```

`src/app/app.config.ts`:

```ts
import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, withComponentInputBinding, withViewTransitions } from '@angular/router';
import { provideHttpClient, withInterceptors, withFetch } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';
import Aura from '@primeng/themes/aura';
import { routes } from './app.routes';
import { authInterceptor } from './core/http/auth.interceptor';
import { errorInterceptor } from './core/http/error.interceptor';
import { apiBaseInterceptor } from './core/http/api-base.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding(), withViewTransitions()),
    provideHttpClient(withFetch(), withInterceptors([apiBaseInterceptor, authInterceptor, errorInterceptor])),
    provideAnimationsAsync(),
    providePrimeNG({ theme: { preset: Aura, options: { darkModeSelector: '.dark' } }, ripple: true }),
  ],
};
```

`app.component.ts`:

```ts
import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({ selector: 'app-root', standalone: true, imports: [RouterOutlet], template: `<router-outlet />` })
export class AppComponent {}
```

---

## 5. Functional HTTP interceptors (JWT + refresh)

Ordered: base URL → auth/refresh → error mapping. Single-flight refresh using a `BehaviorSubject` lock so parallel 401s queue behind one refresh call.

`api-base.interceptor.ts`:

```ts
import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export const apiBaseInterceptor: HttpInterceptorFn = (req, next) =>
  req.url.startsWith('http') ? next(req) : next(req.clone({ url: `${environment.apiBaseUrl}${req.url}` }));
```

`auth.interceptor.ts`:

```ts
import { HttpInterceptorFn, HttpErrorResponse, HttpRequest, HttpHandlerFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { BehaviorSubject, catchError, filter, switchMap, take, throwError } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { TokenStorage } from '../auth/token.storage';

let isRefreshing = false;
const refreshSubject = new BehaviorSubject<string | null>(null);
const addAuth = (r: HttpRequest<unknown>, t: string) => r.clone({ setHeaders: { Authorization: `Bearer ${t}` } });

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const tokens = inject(TokenStorage);
  const auth = inject(AuthService);
  const access = tokens.access();
  const authed = access ? addAuth(req, access) : req;

  return next(authed).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status !== 401 || req.url.includes('/auth/refresh')) return throwError(() => err);
      return handle401(req, next, auth, tokens);
    }),
  );
};

function handle401(req: HttpRequest<unknown>, next: HttpHandlerFn, auth: AuthService, tokens: TokenStorage) {
  if (isRefreshing) {
    return refreshSubject.pipe(filter((t): t is string => !!t), take(1), switchMap((t) => next(addAuth(req, t))));
  }
  isRefreshing = true;
  refreshSubject.next(null);
  return auth.refresh().pipe(
    switchMap((res) => {
      isRefreshing = false;
      tokens.set(res.accessToken, res.refreshToken);
      refreshSubject.next(res.accessToken);
      return next(addAuth(req, res.accessToken));
    }),
    catchError((err) => { isRefreshing = false; auth.logout(); return throwError(() => err); }),
  );
}
```

`error.interceptor.ts`:

```ts
import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { MessageService } from 'primeng/api';
import { catchError, throwError } from 'rxjs';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(MessageService, { optional: true });
  return next(req).pipe(catchError((err: HttpErrorResponse) => {
    if (err.status >= 500) toast?.add({ severity: 'error', summary: 'Server error', detail: err.message });
    else if (err.status === 403) toast?.add({ severity: 'warn', summary: 'Forbidden' });
    return throwError(() => err);
  }));
};
```

---

## 6. Auth guard — `CanMatchFn`

`CanMatch` runs before the lazy chunk is downloaded, so unauthorized users never fetch the bundle.

```ts
import { CanMatchFn, Router, UrlTree } from '@angular/router';
import { inject } from '@angular/core';
import { AuthStore } from './auth.store';

export const authMatchGuard: CanMatchFn = (): boolean | UrlTree => {
  const auth = inject(AuthStore);
  return auth.isAuthenticated() ? true : inject(Router).createUrlTree(['/login']);
};

export const roleMatchGuard = (role: string): CanMatchFn => () => {
  const auth = inject(AuthStore);
  return auth.hasRole(role) ? true : inject(Router).createUrlTree(['/dashboard']);
};
```

---

## 7. Signal store — links list with filter + sort

`@ngrx/signals` SignalStore (`withState` / `withComputed` / `withMethods` / `withHooks`) — no reducer/action/effect boilerplate.

```ts
import { computed, inject } from '@angular/core';
import { signalStore, withState, withComputed, withMethods, withHooks, patchState } from '@ngrx/signals';
import { rxMethod } from '@ngrx/signals/rxjs-interop';
import { pipe, switchMap, tap } from 'rxjs';
import { LinksApi, LinkDto } from './links.api';

export type LinkSort = 'created_desc' | 'created_asc' | 'clicks_desc';

type LinksState = {
  items: LinkDto[]; loading: boolean; error: string | null;
  query: string; sort: LinkSort; page: number; pageSize: number; total: number;
};

const initial: LinksState = {
  items: [], loading: false, error: null,
  query: '', sort: 'created_desc', page: 1, pageSize: 20, total: 0,
};

export const LinksStore = signalStore(
  { providedIn: 'root' },
  withState(initial),
  withComputed((s) => ({
    filtered: computed(() => {
      const q = s.query().toLowerCase();
      const list = q
        ? s.items().filter((l) => l.slug.toLowerCase().includes(q) || l.targetUrl.toLowerCase().includes(q))
        : s.items();
      const sorted = [...list];
      switch (s.sort()) {
        case 'created_asc':  sorted.sort((a, b) => +new Date(a.createdAt) - +new Date(b.createdAt)); break;
        case 'clicks_desc':  sorted.sort((a, b) => b.clickCount - a.clickCount); break;
        default:             sorted.sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt));
      }
      return sorted;
    }),
    isEmpty: computed(() => !s.loading() && s.items().length === 0),
  })),
  withMethods((store, api = inject(LinksApi)) => ({
    setQuery(query: string) { patchState(store, { query, page: 1 }); },
    setSort(sort: LinkSort) { patchState(store, { sort }); },
    setPage(page: number)   { patchState(store, { page }); },
    load: rxMethod<void>(pipe(
      tap(() => patchState(store, { loading: true, error: null })),
      switchMap(() => api.list({ page: store.page(), pageSize: store.pageSize(), q: store.query(), sort: store.sort() })),
      tap({
        next: (res) => patchState(store, { items: res.items, total: res.total, loading: false }),
        error: (e: Error) => patchState(store, { error: e.message, loading: false }),
      }),
    )),
    add(link: LinkDto) { patchState(store, { items: [link, ...store.items()], total: store.total() + 1 }); },
    remove(id: string) {
      patchState(store, { items: store.items().filter((l) => l.id !== id), total: store.total() - 1 });
    },
  })),
  withHooks({ onInit(store) { store.load(); } }),
);
```

---

## 8. Lazy-loaded routes

`app.routes.ts`:

```ts
import { Routes } from '@angular/router';
import { authMatchGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: '', loadChildren: () => import('./features/auth/auth.routes').then((m) => m.AUTH_ROUTES) },
  {
    path: 'dashboard',
    canMatch: [authMatchGuard],
    loadComponent: () => import('./features/dashboard/dashboard-shell.component').then((m) => m.DashboardShellComponent),
    loadChildren: () => import('./features/dashboard/dashboard.routes').then((m) => m.DASHBOARD_ROUTES),
  },
  { path: '**', redirectTo: 'dashboard' },
];
```

`features/dashboard/dashboard.routes.ts`:

```ts
import { Routes } from '@angular/router';

export const DASHBOARD_ROUTES: Routes = [
  { path: '',         loadComponent: () => import('./overview.page').then((m) => m.OverviewPage) },
  { path: 'links',    loadChildren: () => import('../links/links.routes').then((m) => m.LINKS_ROUTES) },
  { path: 'domains',  loadChildren: () => import('../domains/domains.routes').then((m) => m.DOMAINS_ROUTES) },
  { path: 'api-keys', loadChildren: () => import('../api-keys/api-keys.routes').then((m) => m.API_KEYS_ROUTES) },
  { path: 'webhooks', loadChildren: () => import('../webhooks/webhooks.routes').then((m) => m.WEBHOOKS_ROUTES) },
  { path: 'settings', loadChildren: () => import('../settings/settings.routes').then((m) => m.SETTINGS_ROUTES) },
];
```

`features/links/links.routes.ts`:

```ts
import { Routes } from '@angular/router';

export const LINKS_ROUTES: Routes = [
  { path: '',    loadComponent: () => import('./links-list.page').then((m) => m.LinksListPage) },
  { path: ':id', loadComponent: () => import('./link-detail.page').then((m) => m.LinkDetailPage) },
];
```

---

## 9. Reactive form — create-link (strictly typed)

`NonNullableFormBuilder` + custom URL validator + async slug-uniqueness validator.

```ts
import { Component, inject, signal } from '@angular/core';
import {
  NonNullableFormBuilder, ReactiveFormsModule, Validators,
  AbstractControl, AsyncValidatorFn, ValidationErrors,
} from '@angular/forms';
import { of, map, catchError, debounceTime, switchMap, first } from 'rxjs';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { LinksApi } from './links.api';
import { LinksStore } from './links.store';

const urlValidator = (ctrl: AbstractControl): ValidationErrors | null => {
  const v = ctrl.value as string;
  if (!v) return null;
  try { new URL(v); return null; } catch { return { url: true }; }
};

const slugUniqueValidator = (api: LinksApi): AsyncValidatorFn => (ctrl) =>
  ctrl.valueChanges.pipe(
    debounceTime(300),
    switchMap((v: string) => v ? api.checkSlug(v) : of({ available: true })),
    map((r) => r.available ? null : { taken: true }),
    catchError(() => of(null)), first(),
  );

@Component({
  selector: 'app-link-create',
  standalone: true,
  imports: [ReactiveFormsModule, ButtonModule, InputTextModule],
  template: `
    <form [formGroup]="form" (ngSubmit)="submit()" class="space-y-3">
      <label class="block">
        <span class="text-sm">Target URL</span>
        <input pInputText formControlName="targetUrl" class="w-full" />
        @if (form.controls.targetUrl.touched && form.controls.targetUrl.errors?.['url']) {
          <small class="text-red-500">Must be a valid URL</small>
        }
      </label>
      <label class="block">
        <span class="text-sm">Custom slug (optional)</span>
        <input pInputText formControlName="slug" class="w-full" />
        @if (form.controls.slug.errors?.['taken']) { <small class="text-red-500">Already taken</small> }
      </label>
      <label class="block">
        <span class="text-sm">Expires at (optional)</span>
        <input type="datetime-local" formControlName="expiresAt" class="w-full" />
      </label>
      <button pButton type="submit" [disabled]="form.invalid || submitting()">
        {{ submitting() ? 'Creating…' : 'Create' }}
      </button>
    </form>
  `,
})
export class LinkCreateDialog {
  private fb = inject(NonNullableFormBuilder);
  private api = inject(LinksApi);
  private store = inject(LinksStore);
  submitting = signal(false);

  form = this.fb.group({
    targetUrl: this.fb.control('', { validators: [Validators.required, urlValidator] }),
    slug: this.fb.control('', {
      validators: [Validators.pattern(/^[a-zA-Z0-9_-]{3,32}$/)],
      asyncValidators: [slugUniqueValidator(this.api)],
    }),
    expiresAt: this.fb.control(''),
  });

  submit(): void {
    if (this.form.invalid) return;
    this.submitting.set(true);
    const v = this.form.getRawValue();
    this.api.create({ targetUrl: v.targetUrl, slug: v.slug || undefined, expiresAt: v.expiresAt || undefined })
      .subscribe({
        next: (link) => { this.store.add(link); this.form.reset(); this.submitting.set(false); },
        error: () => this.submitting.set(false),
      });
  }
}
```

---

## 10. API client — `inject(HttpClient)` + signals

```ts
import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';

export interface LinkDto {
  id: string; slug: string; targetUrl: string; clickCount: number;
  createdAt: string; expiresAt: string | null; domainId: string | null;
}
export interface LinksPage { items: LinkDto[]; total: number; }
export interface CreateLinkReq { targetUrl: string; slug?: string; expiresAt?: string; }

@Injectable({ providedIn: 'root' })
export class LinksApi {
  private http = inject(HttpClient);
  readonly lastFetchAt = signal<number | null>(null);

  list(o: { page: number; pageSize: number; q: string; sort: string }): Observable<LinksPage> {
    const params = new HttpParams().set('page', o.page).set('pageSize', o.pageSize).set('q', o.q).set('sort', o.sort);
    return this.http.get<LinksPage>('/api/v1/links', { params });
  }
  get(id: string)    { return this.http.get<LinkDto>(`/api/v1/links/${id}`); }
  create(req: CreateLinkReq) { return this.http.post<LinkDto>('/api/v1/links', req); }
  delete(id: string) { return this.http.delete<void>(`/api/v1/links/${id}`); }
  checkSlug(slug: string) {
    return this.http.get<{ available: boolean }>('/api/v1/links/slug-check',
      { params: new HttpParams().set('slug', slug) });
  }
  analytics(id: string, range: '24h' | '7d' | '30d') {
    return this.http.get<{ points: { t: string; clicks: number }[] }>(
      `/api/v1/links/${id}/analytics`, { params: new HttpParams().set('range', range) });
  }
}
```

---

## 11. `nginx.conf` — SPA fallback + asset cache

```nginx
worker_processes auto;
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  sendfile on; tcp_nopush on; keepalive_timeout 65;

  gzip on; gzip_comp_level 6; gzip_min_length 1024;
  gzip_types text/plain text/css application/javascript application/json
             application/xml image/svg+xml font/woff2;

  server {
    listen 8080;
    root /usr/share/nginx/html;
    index index.html;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location ~* \.(js|css|woff2|woff|ttf|png|jpg|jpeg|gif|svg|ico)$ {
      expires 1y; access_log off;
      add_header Cache-Control "public, immutable";
      try_files $uri =404;
    }
    location = /index.html { add_header Cache-Control "no-store, no-cache, must-revalidate"; }
    location / { try_files $uri $uri/ /index.html; }
  }
}
```

---

## 12. Multistage Dockerfile

```dockerfile
# ---- build ----
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG BUILD_CONFIG=production
RUN npm run build -- --configuration=${BUILD_CONFIG}

# ---- serve ----
FROM nginx:1.25-alpine AS runtime
RUN addgroup -S app && adduser -S app -G app \
 && mkdir -p /var/cache/nginx /var/run /var/log/nginx \
 && chown -R app:app /var/cache/nginx /var/run /var/log/nginx /usr/share/nginx/html

COPY --from=builder /app/dist/shrtnr-admin/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -q --spider http://localhost:8080/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
```

Build: `docker build -t shrtnr/admin:latest .`
Run:   `docker run --rm -p 8080:8080 shrtnr/admin:latest`

Note: Angular 19's esbuild output lives at `dist/<project>/browser/`, not `dist/<project>/` — the `COPY` path must reflect that.

---

## 13. Environment config + `fileReplacements`

`environment.ts` (dev default):

```ts
export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8080',
  appName: 'shrtnr admin (dev)',
  enableAnalyticsBeta: true,
};
```

`environment.staging.ts` / `environment.prod.ts` have the same shape with production URLs and `production: true`.

`angular.json` → `architect.build.configurations`:

```json
{
  "production": {
    "fileReplacements": [
      { "replace": "src/environments/environment.ts", "with": "src/environments/environment.prod.ts" }
    ],
    "optimization": true, "outputHashing": "all", "sourceMap": false,
    "namedChunks": false, "extractLicenses": true,
    "budgets": [
      { "type": "initial", "maximumWarning": "500kb", "maximumError": "1mb" },
      { "type": "anyComponentStyle", "maximumWarning": "4kb", "maximumError": "10kb" }
    ]
  },
  "staging": {
    "fileReplacements": [
      { "replace": "src/environments/environment.ts", "with": "src/environments/environment.staging.ts" }
    ],
    "optimization": true, "outputHashing": "all", "sourceMap": true
  },
  "development": { "optimization": false, "sourceMap": true, "namedChunks": true }
}
```

Always import from the neutral path so replacement works: `import { environment } from '../environments/environment';`. Runtime overrides (hotfix API URL without rebuild) load via `APP_INITIALIZER` fetching `/assets/config.json`; mount an override into the nginx container if needed.

---

## 14. Page inventory

| Route                    | Component                                       | Guard            | Notes |
|--------------------------|-------------------------------------------------|------------------|-------|
| `/login`                 | `features/auth/login.page.ts`                   | —                | PrimeNG Card + reactive form |
| `/register`              | `features/auth/register.page.ts`                | —                | Optional; feature-flag off if invite-only |
| `/dashboard`             | `features/dashboard/overview.page.ts`           | `authMatchGuard` | KPI tiles, timeseries chart |
| `/dashboard/links`       | `features/links/links-list.page.ts`             | `authMatchGuard` | `p-table` server paging, filter, create dialog |
| `/dashboard/links/:id`   | `features/links/link-detail.page.ts`            | `authMatchGuard` | Metadata editor, QR, analytics charts, referrers |
| `/dashboard/domains`     | `features/domains/domains-list.page.ts`         | `authMatchGuard` | Custom domain CRUD, DNS-verify badges |
| `/dashboard/api-keys`    | `features/api-keys/api-keys.page.ts`            | `authMatchGuard` | Create/revoke, show token **once**, scope checkboxes |
| `/dashboard/webhooks`    | `features/webhooks/webhooks.page.ts`            | `authMatchGuard` | Endpoint CRUD, deliveries table with retry |
| `/dashboard/settings`    | `features/settings/settings.page.ts`            | `authMatchGuard` | Profile, password, 2FA, sessions |

Shell: `DashboardShellComponent` = PrimeNG `p-menu` sidebar + `p-menubar` topbar + `<router-outlet>`. Heavy side panels behind `@defer (on idle)`.

---

## 15. Chart library — **ApexCharts via `ng-apexcharts`**

Why:

- **Dashboard fit**: line, area, bar, donut, heatmap, radial, mixed — all the shapes the link-analytics page needs, out of the box.
- **Interactivity**: zoom, pan, brush, tooltips, annotations via declarative `ApexOptions`.
- **Real-time**: `chart.updateSeries()` streams well for live click counters wired from Redis Streams.
- **Rendering**: SVG — crisp on retina, themeable via CSS variables, native SVG/PNG/CSV export.
- **Bundle cost**: ~150 KB gzipped, acceptable, lazy-loaded on the analytics route via `@defer`.

Rejected: **ngx-charts** (tiny community, fewer chart types, heavy D3 hand-rolling); **Chart.js + ng2-charts** (canvas, weaker interactivity, wrapper lags behind).

```ts
import { Component, computed, inject, input, signal } from '@angular/core';
import { NgApexchartsModule, ApexOptions } from 'ng-apexcharts';
import { toSignal } from '@angular/core/rxjs-interop';
import { LinksApi } from './links.api';

@Component({
  selector: 'app-link-chart',
  standalone: true,
  imports: [NgApexchartsModule],
  template: `
    @defer (on viewport) {
      <apx-chart [series]="opts().series!" [chart]="opts().chart!"
                 [xaxis]="opts().xaxis!" [stroke]="opts().stroke!" />
    } @placeholder { <div class="h-64 animate-pulse bg-slate-100"></div> }
  `,
})
export class LinkChart {
  id = input.required<string>();
  private api = inject(LinksApi);
  range = signal<'24h' | '7d' | '30d'>('7d');

  data = toSignal(computed(() => this.api.analytics(this.id(), this.range()))(),
    { initialValue: { points: [] as { t: string; clicks: number }[] } });

  opts = computed<ApexOptions>(() => ({
    chart:  { type: 'area', height: 260, toolbar: { show: false } },
    stroke: { curve: 'smooth', width: 2 },
    series: [{ name: 'Clicks', data: this.data().points.map((p) => [p.t, p.clicks]) }],
    xaxis:  { type: 'datetime' },
  }));
}
```

---

## Operational checklist

- [ ] `npm ci` in CI, not `npm install`.
- [ ] `ng build --configuration production` outputs `dist/shrtnr-admin/browser`.
- [ ] Docker image ≤ 50 MB (`docker images`).
- [ ] Container `HEALTHCHECK` green.
- [ ] Access token in memory only; refresh in `httpOnly` cookie.
- [ ] `CanMatchFn` on every lazy route under `/dashboard`.
- [ ] Heavy charts behind `@defer (on viewport)`.
- [ ] Initial-bundle budget: warn 500 KB, error 1 MB.
- [ ] Control flow (`@if / @for / @switch`) in all new code; `track` on every `@for`.
