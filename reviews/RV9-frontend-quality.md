# RV9 — Admin-Panel Frontend Quality Audit

Scope: `admin-panel/src/app/**`, `angular.json`, `tsconfig.json`, `package.json` (Angular 19, standalone, signals).

Overall the project is modernized well: all 17 components are standalone + `OnPush`, templates use `@if`/`@for`, routing uses `loadComponent`/`loadChildren` + `CanMatchFn`, interceptors are functional, DI is `inject()`-based, no `NgModule`, no `any`, no `*ngIf`/`*ngFor`. ApexCharts is lazy-loaded via `@defer (on viewport)`. `apiBaseInterceptor` centralizes the base URL. Budgets are set. Issues below, ranked.

---

## 1. Blockers

### B1. Wrong API path — password change will 404
`features/settings/settings.component.ts:117` posts to `/auth/password`, but every other auth call and the backend routing use the `/v1/...` prefix. With the `apiBaseInterceptor` prepending `/api`, the request goes to `/api/auth/password` instead of `/api/v1/auth/password`.

Patch (`settings.component.ts:117`):
```ts
-      await firstValueFrom(this.api.post<void>('/auth/password', this.passwordForm.getRawValue()));
+      await firstValueFrom(this.api.post<void>('/v1/auth/password', this.passwordForm.getRawValue()));
```

### B2. Memory leak — 4 unmanaged subscriptions in `detail.component.ts`
`detail.component.ts:214, 228, 232, 236` all call `.subscribe()` without `takeUntilDestroyed()`. `changeRange()` triggers three more subs each click — old in-flight requests race and overwrite newer ones. Also leaks if the user navigates away mid-request.

Patch — inject `DestroyRef` and add `takeUntilDestroyed(this.destroyRef)` to every pipe. Import:
```ts
import { DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
```
Inside the class:
```ts
  private readonly destroyRef = inject(DestroyRef);
```
Then on every `.subscribe` in `ngOnInit` + `loadAnalytics()`:
```ts
this.analyticsApi.timeseries(id, r).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ ... });
```
Same treatment in `overview.component.ts:112`, `landing.component.ts:116`, `login.component.ts:80`, `register.component.ts:83`, and `auth.service.ts:62/70/166` (use `takeUntilDestroyed()` in injection context or `take(1)` for one-shot HTTP).

### B3. Duplicate envelope-unwrap boilerplate in `auth.service.ts`
`auth.service.ts:83-117` and `126-160` re-implement the `{success, data} | {success, error}` unwrap that already lives in `ApiService.post`. Swap to the existing `AuthApi` (`core/api/auth.api.ts` — already written, currently unused).

Patch (`auth.service.ts:28, 83-117, 140-155`):
```ts
-  private readonly http = inject(HttpClient);
+  private readonly authApi = inject(AuthApi);
...
   login(req: LoginRequest): Observable<User> {
-    return this.http.post<{success:true,data:TokenPair}|{success:false,error:{message:string}}>(
-      `/v1/auth/login`, req,
-    ).pipe(
-      map((r) => { if (!('success' in r) || !r.success) throw new Error((r as any).error.message); return r.data; }),
-      tap((pair) => this.applyTokenPair(pair)),
-      map((pair) => pair.user),
-    );
+    return this.authApi.login(req).pipe(
+      tap((pair) => this.applyTokenPair(pair)),
+      map((pair) => pair.user),
+    );
   }
```
Apply the identical shape to `register()` and `refresh()`. Delete `HttpClient` import. Removes ~40 lines.

---

## 2. High-impact fixes

### H1. `auth.service.refresh()` single-flight — pre-localStorage edge case
`auth.service.ts:126-160`. If `refresh()` is invoked before localStorage is readable (SSR/private-mode throw caught in `readRefreshToken`), it correctly returns `throwError`. But when `isRefreshing` is already `true` and `refreshSubject` still holds `null`, a second caller blocks forever on `filter(t !== null)` if the first call errors — `finalize` resets `isRefreshing` but never pushes `null`/error to the subject.

Patch (`auth.service.ts:138-159`):
```ts
-    return this.http.post<...>(`/v1/auth/refresh`, { refresh_token: rt }).pipe(
-      switchMap((r) => { ... }),
-      finalize(() => { this.isRefreshing = false; }),
-    );
+    return this.http.post<...>(`/v1/auth/refresh`, { refresh_token: rt }).pipe(
+      switchMap((r) => {
+        if (!('success' in r) || !r.success) {
+          this.refreshSubject.error(new Error((r as any).error.message));
+          return throwError(() => new Error((r as any).error.message));
+        }
+        const d = r.data;
+        this.accessToken.set(d.access_token);
+        this.writeRefreshToken(d.refresh_token);
+        this.refreshSubject.next(d.access_token);
+        return of(d.access_token);
+      }),
+      catchError((err) => { this.refreshSubject.error(err); return throwError(() => err); }),
+      finalize(() => { this.isRefreshing = false; this.refreshSubject = new BehaviorSubject<string | null>(null); }),
+    );
```
(Reset the subject on finalize so the next refresh cycle starts clean.)

### H2. Login double-submit guard — button disables but pending requests race
`login.component.ts:80`, `register.component.ts:83`. `busy()` disables the button, but nothing prevents `submit()` being re-entered via Enter key while `busy()` is already `true`. Add a guard.

Patch (`login.component.ts:76-79`, identical for register):
```ts
   submit(): void {
-    if (this.form.invalid) return;
+    if (this.form.invalid || this.busy()) return;
     this.error.set(null);
     this.busy.set(true);
```

### H3. `list.component.ts` — `@for` uses `track link.id` implicitly via `dataKey` but sidebar list doesn't
`main-layout.component.html:30` uses `track item.route` — good. But `dashboard/overview.component.ts:33` does `@for (i of skeletons; track i)` — fine. `webhooks.component.ts:46` tracks `e` (string) — fine. No issues actually — but **table rows** in PrimeNG already track via `dataKey="id"`. Keep.

### H4. `.subscribe()` in `auth.service.ts:70` nested inside another `.subscribe()`
Classic nested-subscribe antipattern. Flatten with `switchMap`.

Patch (`auth.service.ts:62-80`):
```ts
-    this.refresh().subscribe({
-      next: () => {
-        this.http.get<...>(`/v1/users/me`, { headers: ... }).subscribe({
-          next: (r) => { if ('success' in r && r.success) this.user.set(r.data); },
-          error: () => void 0,
-        });
-      },
-      error: () => { this.clearSession(); },
-    });
+    this.refresh().pipe(
+      switchMap(() => this.authApi.me()),
+      takeUntilDestroyed(),
+    ).subscribe({
+      next: (u) => this.user.set(u),
+      error: () => this.clearSession(),
+    });
```

### H5. `publicShortHost` fallback reads `globalThis.location` in `computed()` — SSR hazard + impure
`list.component.ts:157` and `detail.component.ts:191`. `computed()` should be pure of side-effects; `globalThis.location.origin` is fine at runtime but unpredictable under SSR. Move into a small `environment` helper, or gate on `typeof window !== 'undefined'`. Low-severity, but worth noting for later SSR adoption.

### H6. `console.log` / silent catches
`auth.service.ts:74` `error: () => void 0`; `detail.component.ts:220, 231, 235, 239` `error: () => ...` swallow without toast. The global `errorInterceptor` only surfaces 5xx/403/429 — `401/400/404/422` on these paths go silent. Add a per-call toast for detail fetch failures (at least for 404 "Link not found" which is already rendered as fallback — OK) but the three analytics subs silently hide errors.

Patch (`detail.component.ts:229, 233, 237`): add `error: (e) => this.toast.add({ severity: 'warn', summary: 'Analytics unavailable', detail: (e as Error).message })` — or at minimum log.

---

## 3. Polish

### P1. `NgOptimizedImage` for QR image
`detail.component.ts:99` — `<img [src]="qr" ...>`. Data-URL images can't use `NgOptimizedImage`, so keep as-is. No change.

### P2. `debounceTime` on list search is hand-rolled via `setTimeout`
`list.component.ts:150-154`. Works, but RxJS-native is cleaner and auto-cleans.

Patch (`list.component.ts`): replace `search` signal + `searchTimer` with `toSignal(valueChanges.pipe(debounceTime(300)))`, or wire `(ngModelChange)` into a `Subject` + `takeUntilDestroyed` + `debounceTime(300)`.

### P3. `skeletons = [1,2,3,4]` uses index as track key
`overview.component.ts:89, 33` — fine but can be `track $index` for clarity:
```ts
-@for (i of skeletons; track i) {
+@for (i of skeletons; track $index) {
```

### P4. `create.component.ts` async validator — `first()` inside `switchMap`
`create.component.ts:38`. `first()` after `map` works, but cleaner: use `api.checkAlias(v).pipe(map(...), catchError(...))` and rely on the outer async-validator semantics (Angular subscribes once). Current code subscribes to `valueChanges`, which double-runs and can race. Use `of(ctrl.value).pipe(debounceTime(350), switchMap(...))` instead of `ctrl.valueChanges`.

Patch (`create.component.ts:31-40`):
```ts
 function aliasUniqueValidator(api: UrlsApi): AsyncValidatorFn {
   return (ctrl: AbstractControl): Observable<ValidationErrors | null> =>
-    ctrl.valueChanges.pipe(
-      debounceTime(350),
-      switchMap((v: string) => (v ? api.checkAlias(v) : of({ available: true }))),
-      map((r) => (r.available ? null : { taken: true })),
-      catchError(() => of(null)),
-      first(),
-    );
+    timer(350).pipe(
+      switchMap(() => (ctrl.value ? api.checkAlias(ctrl.value as string) : of({ available: true }))),
+      map((r) => (r.available ? null : { taken: true })),
+      catchError(() => of(null)),
+    );
 }
```
(Import `timer` from rxjs; drop `debounceTime, first, valueChanges` usage.)

### P5. `expires_at: this.fb.control<Date | null>(null as unknown as Date)`
`create.component.ts:128`. `NonNullableFormBuilder` forces non-null; the cast is a smell. Swap to plain `FormBuilder` for that one control, or:
```ts
-      expires_at: this.fb.control<Date | null>(null as unknown as Date),
+      expires_at: new FormControl<Date | null>(null),
```
(import `FormControl`).

### P6. Unsaved-form-changes warning
No `CanDeactivate` guard on `create.component.ts` or `settings.component.ts`. Nice-to-have: prompt on navigation when `form.dirty`.

### P7. `settings.component` profile form initialized from `user()` signal snapshot at class-field time
`settings.component.ts:83-87`. If `user()` loads after component creation (e.g. via bootstrap refresh), the form stays empty. Either:
- use `effect(() => this.profileForm.patchValue({ name: u.full_name, email: u.email }))`, or
- guard navigation to `/settings` until `user()` is present.

### P8. `api.service.ts` silent `assertSuccess` error path
`api.service.ts:78-82`. Uses plain `new Error(msg)` — loses status code, code, and field errors. Consider an `ApiException extends Error { code; fields; status }` so callers can do typed branching (e.g. 422 field errors in forms).

### P9. `publicShortHost` env key — dev environment hardcodes `http://localhost`
`environment.ts:4`. Fine for dev, but `environment.prod.ts:4` is empty string, relying on `globalThis.location.origin`. Document or set explicitly per-env.

### P10. Bundle — ApexCharts via `ng-apexcharts@1.15.0` + `apexcharts@^4.0.0`
ng-apexcharts 1.x only declares peer on apexcharts 3.x — v4 may break at runtime. Downgrade `apexcharts` to `^3` or upgrade `ng-apexcharts` to a v4-compatible release. Check `npm ls apexcharts` in CI.

### P11. `provideZoneChangeDetection({ eventCoalescing: true })`
`app.config.ts:16`. Good. For Angular 19 zoneless-ready prep, consider `provideExperimentalZonelessChangeDetection()` once all components are fully signal-driven (they are — try it).

### P12. `noPropertyAccessFromIndexSignature` enabled
`tsconfig.json:8`. Strict. Good.

### P13. `@ngrx/signals` in deps but unused
`package.json:29`. `LinksStore` is hand-rolled signals. Either adopt signalStore or drop the dep to save bundle.

---

## Summary

- 3 blockers: wrong `/auth/password` URL, 7+ unmanaged `.subscribe()` leaks in `detail.component.ts`/others, duplicated envelope unwrap in `auth.service.ts`.
- Strong foundation: OnPush everywhere, new control flow, standalone, functional interceptors, signals-first, lazy routes, `@defer` for charts, proper tsconfig strictness, no `any`, no `*ngIf`.
- No `environment.apiBaseUrl` leakage outside the interceptor — clean.
- Guard B2 and H4 are the most important runtime fixes.
