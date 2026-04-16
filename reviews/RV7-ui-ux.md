# RV7 — Admin Panel UI/UX Review

Scope: Angular 19 + PrimeNG admin panel + landing page. Reviewed dashboard,
links (list/create/detail), auth, landing, settings, api-keys, domains,
webhooks, main layout, styles.scss, tailwind.config.js.

Legend: file paths are absolute, line references point at the **current**
source. Code snippets are meant to be applied literally by a fixer.

---

## 1. Blockers (broken features, confusing flows)

### B1. `overview.component.ts` treats *any* API error as "No data yet"

`admin-panel/src/app/features/dashboard/overview.component.ts` lines 111-121 —
the error handler silently sets `loading=false` and leaves `stats()` null,
which the template then renders as the *empty* state ("Create your first
short link"). A 401, 500, or network failure is indistinguishable from a
brand-new account.

Fix — surface an error branch and a retry button:

```ts
readonly error = signal<string | null>(null);
// ...
constructor() {
  this.load();
}
load(): void {
  this.loading.set(true);
  this.error.set(null);
  this.analytics.overview().subscribe({
    next: (s) => { this.stats.set(s); this.loading.set(false); },
    error: (e: { message?: string }) => {
      this.error.set(e?.message ?? 'Could not load overview.');
      this.loading.set(false);
    },
  });
}
```

And in the template, replace the `@else` fallback with:

```html
@else if (error(); as e) {
  <app-empty-state icon="pi pi-exclamation-triangle"
                   title="Couldn't load overview"
                   [description]="e">
    <button pButton class="btn-primary mt-4" (click)="load()" label="Retry"></button>
  </app-empty-state>
} @else {
  <app-empty-state icon="pi pi-chart-bar"
                   title="No data yet"
                   description="Create your first short link to start seeing analytics.">
    <a routerLink="/dashboard/links/new" class="btn-primary mt-4">Create a link</a>
  </app-empty-state>
}
```

Apply the same pattern to `detail.component.ts` lines 213-223 (both
`urlsApi.get` and every `analyticsApi.*` call swallow errors).

### B2. Landing "Shorten" flow has no client-side URL normalization

`landing.component.ts` lines 104-111 calls `new URL(url)` with no scheme
coercion, so pasting `example.com` fails with a confusing "not a valid URL"
message. Real shorteners auto-prefix `https://`.

```ts
shorten(): void {
  let url = this.longUrl().trim();
  if (!url) return;
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
  try { new URL(url); }
  catch { this.error.set('That does not look like a valid URL.'); return; }
  this.longUrl.set(url);
  // ... rest unchanged
}
```

### B3. Sidebar does not collapse on mobile — no drawer

`main-layout.component.html` lines 3-6 always render the aside at `w-64` or
`w-16`. On a <768px viewport the 64-unit sidebar eats most of the screen and
there is no overlay/drawer behaviour. Add a `mobileOpen` signal and slide-in
classes:

```ts
// main-layout.component.ts
readonly mobileOpen = signal(false);
toggleMobile(): void { this.mobileOpen.update(v => !v); }
```

```html
<!-- main-layout.component.html -->
<aside
  class="fixed inset-y-0 left-0 z-40 flex flex-col border-r border-slate-200 bg-white
         transition-transform duration-200 scrollbar-thin md:static md:translate-x-0"
  [class.w-64]="!collapsed()"
  [class.w-16]="collapsed()"
  [class.-translate-x-full]="!mobileOpen()"
  [class.translate-x-0]="mobileOpen()">
  ...
</aside>

<!-- Mobile header button, inside the header div -->
<button type="button" class="btn-ghost md:hidden" (click)="toggleMobile()"
        aria-label="Open menu">
  <i class="pi pi-bars"></i>
</button>
```

### B4. `list.component.ts` table `responsiveLayout="scroll"` is set but sort is configured wrong

`list.component.ts` line 65 asks for scroll responsiveness, but the `<th>`
columns are not marked `pSortableColumn`, so clicking a header does nothing
while `onLazy` still tries to read `event.sortField` (line 143). Sorting
advertises itself but never fires. Either drop the sort branch in `onLazy` or
wire the headers:

```html
<th pSortableColumn="short_code">Short <p-sortIcon field="short_code"/></th>
<th pSortableColumn="long_url">Target <p-sortIcon field="long_url"/></th>
<th pSortableColumn="click_count" class="text-right">Clicks <p-sortIcon field="click_count"/></th>
<th>Status</th>
<th pSortableColumn="created_at">Created <p-sortIcon field="created_at"/></th>
<th class="text-right">Actions</th>
```

(Also add `SortIconModule` / `import { SortIconModule } from 'primeng/sorticon';` or use built-in `p-table` sort with `[sortField]`/`[sortOrder]` state.)

---

## 2. High-impact improvements

### H1. No dark mode toggle despite plumbed theme

`tailwind.config.js` line 4 sets `darkMode: 'class'` and
`app.config.ts` line 28 configures PrimeNG with
`darkModeSelector: '.dark'` — but **nothing ever toggles the `.dark` class**
and no UI exposes it. Either remove the pretense or add a toggle in the
topbar:

```ts
// main-layout.component.ts
readonly darkMode = signal(localStorage.getItem('theme') === 'dark');
constructor() {
  effect(() => {
    document.documentElement.classList.toggle('dark', this.darkMode());
    localStorage.setItem('theme', this.darkMode() ? 'dark' : 'light');
  });
}
toggleDark(): void { this.darkMode.update(v => !v); }
```

```html
<!-- main-layout.component.html, in the header actions block before the avatar -->
<button type="button" class="btn-ghost !p-2" (click)="toggleDark()"
        [pTooltip]="darkMode() ? 'Light mode' : 'Dark mode'" tooltipPosition="bottom"
        [attr.aria-label]="darkMode() ? 'Switch to light mode' : 'Switch to dark mode'">
  <i class="pi" [class.pi-moon]="!darkMode()" [class.pi-sun]="darkMode()"></i>
</button>
```

Also: the Tailwind `card`, `btn-primary`, `btn-ghost` utilities in
`styles.scss` lines 17-27 hard-code white/slate with no `dark:` variants —
the toggle will look broken on the dashboard until dark variants are added:

```scss
.card {
  @apply bg-white dark:bg-slate-800 rounded-lg shadow-sm
         border border-slate-200 dark:border-slate-700 p-4;
}
.btn-ghost {
  @apply inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium
         text-slate-700 dark:text-slate-200
         hover:bg-slate-100 dark:hover:bg-slate-700;
}
.form-label { @apply block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1; }
.page-title { @apply text-2xl font-semibold text-slate-900 dark:text-slate-50; }
```

### H2. Forms don't autofocus the first field

`login.component.ts`, `register.component.ts`, `create.component.ts`,
`settings.component.ts`, `domains.component.ts`, `webhooks.component.ts` all
lack autofocus. The dialog in `api-keys.component.ts` (lines 80-108) also
does not autofocus the name input.

For login (applies similarly to others):

```html
<input pInputText id="email" type="email" formControlName="email"
       class="w-full" autocomplete="email" autofocus />
```

For the `api-keys` dialog, use PrimeNG's `pAutoFocus`:

```ts
// api-keys.component.ts imports
import { AutoFocusModule } from 'primeng/autofocus';
// add AutoFocusModule to @Component.imports
```

```html
<input pInputText id="keyname" class="w-full" pAutoFocus [autofocus]="true"
       [ngModel]="name()" (ngModelChange)="name.set($event)" placeholder="CI, webhook…" />
```

### H3. No breadcrumb / page context in top bar

`main-layout.component.html` lines 57-69 show only "Welcome back, name".
On deep pages (e.g. `/dashboard/links/:id`) there's no indication of where
you are. Add a lightweight breadcrumb driven by route data, or at minimum a
page title slot. Quick version using existing nav metadata:

```ts
// main-layout.component.ts
import { Router, NavigationEnd } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map, startWith } from 'rxjs';
// ...
private readonly router = inject(Router);
readonly currentLabel = toSignal(
  this.router.events.pipe(
    filter(e => e instanceof NavigationEnd),
    startWith(null),
    map(() => this.nav.find(n => this.router.url.startsWith(n.route))?.label ?? ''),
  ),
  { initialValue: '' },
);
```

```html
<header class="flex items-center justify-between h-14 px-6 bg-white border-b border-slate-200">
  <div class="flex items-center gap-3">
    <button class="btn-ghost md:hidden" (click)="toggleMobile()" aria-label="Open menu">
      <i class="pi pi-bars"></i>
    </button>
    <span class="text-sm font-medium text-slate-800">{{ currentLabel() }}</span>
  </div>
  <!-- existing right-hand actions -->
</header>
```

### H4. `list.component.ts` search input has no accessible label

`list.component.ts` lines 43-49 — `<input>` has placeholder but no
`aria-label`. Screen readers announce it as unlabeled.

```html
<input pInputText type="text" class="w-full"
       aria-label="Search links"
       placeholder="Search by short code or URL…"
       [ngModel]="search()" (ngModelChange)="onSearch($event)" />
```

Same issue on `domains.component.ts` line 37 and `webhooks.component.ts`
line 39 (the wurl input has an `<label for="wurl">` — good — but domain's
host input has none).

### H5. `create.component.ts` alias validator always shows "Alias already taken" on unrelated errors

`create.component.ts` lines 31-40 — `aliasUniqueValidator` maps any
non-available response to `{ taken: true }` and silently swallows network
errors to `null`. But on a transient 500 the user sees **nothing** (no
spinner, no warning) and submit may still fail on the server. Add pending
state + distinguish:

```ts
function aliasUniqueValidator(api: UrlsApi): AsyncValidatorFn {
  return (ctrl: AbstractControl): Observable<ValidationErrors | null> =>
    of(ctrl.value as string).pipe(
      debounceTime(350),
      switchMap(v =>
        !v ? of(null)
           : api.checkAlias(v).pipe(
               map(r => r.available ? null : { taken: true }),
               catchError(() => of({ checkFailed: true })),
             )),
      first(),
    );
}
```

And in the template (lines 80-83):

```html
@if (form.controls.custom_alias.pending) {
  <div><small class="text-slate-500"><i class="pi pi-spin pi-spinner text-xs"></i> Checking…</small></div>
}
@if (form.controls.custom_alias.errors; as e) {
  @if (e['pattern']) { <div><small class="text-red-500">Invalid format.</small></div> }
  @else if (e['taken']) { <div><small class="text-red-500">Alias already taken.</small></div> }
  @else if (e['checkFailed']) { <div><small class="text-amber-600">Could not check availability.</small></div> }
}
```

Also the validator's `ctrl.valueChanges` source is wrong — an Angular async
validator is called per-change with the *value already there*, so piping
`valueChanges` inside makes it never resolve on the first try. Snippet above
fixes this.

### H6. `detail.component.ts` "Link not found" is unhelpful

`detail.component.ts` line 160 renders `Link not found.` as centered grey
text with no CTA. A user who typed a wrong URL has no way back. Replace:

```html
@else {
  <app-empty-state icon="pi pi-question-circle"
                   title="Link not found"
                   description="This link may have been deleted or you don't have access.">
    <a routerLink="/dashboard/links" class="btn-primary mt-4">Back to links</a>
  </app-empty-state>
}
```

(needs `EmptyStateComponent` in imports — already imported indirectly? No,
currently not. Add it.)

### H7. `detail.component.ts` short URL section has no edit / enable / disable affordance

Users land on the detail page, see the link is `disabled`, but there is no
way to re-enable it, edit the target, or delete from here — they have to go
back to the list. Add an actions row:

```html
<div class="flex items-center gap-2 mb-3">
  <a [href]="shortUrl()" target="_blank" rel="noopener"
     class="font-mono text-brand-600 text-lg break-all hover:underline">{{ shortUrl() }}</a>
  <app-copy-button [value]="shortUrl()" />
  <button pButton icon="pi pi-pencil" class="p-button-sm p-button-text"
          (click)="edit()" pTooltip="Edit" aria-label="Edit"></button>
  <button pButton [icon]="l.is_active ? 'pi pi-pause' : 'pi pi-play'"
          class="p-button-sm p-button-text"
          (click)="toggleActive()"
          [pTooltip]="l.is_active ? 'Disable' : 'Enable'"
          [attr.aria-label]="l.is_active ? 'Disable' : 'Enable'"></button>
  <button pButton icon="pi pi-trash" class="p-button-sm p-button-text p-button-danger"
          (click)="askDelete()" pTooltip="Delete" aria-label="Delete"></button>
</div>
```

Back in the component class, implement `edit/toggleActive/askDelete` using
`UrlsApi.patch` / `UrlsApi.delete` (already used in the store).

### H8. `domains.component.ts` DNS instructions are too terse and the CNAME target is hard-coded

`domains.component.ts` lines 47-49 — the CNAME value
`cname.urlshortener.app` should be pulled from config, and the instructions
should show both *what* to add and *where*:

```html
<div class="text-xs text-slate-500 mt-2 space-y-1">
  <p>1. In your DNS provider, create a <b>CNAME</b> record:</p>
  <pre class="bg-slate-50 border rounded p-2 font-mono text-[11px]">links.example.com  CNAME  {{ cnameTarget }}</pre>
  <p>2. (Optional) add a <b>TXT</b> record for verification with the DNS token below.</p>
  <p>3. Click <b>Verify</b> once DNS propagates (usually &lt;15 min).</p>
</div>
```

```ts
// domains.component.ts
readonly cnameTarget = environment.cnameTarget ?? 'cname.urlshortener.app';
```

### H9. Toast severities used inconsistently

- `domains.component.ts` line 144 uses `severity: 'warn'` for "Still pending" — fine.
- `detail.component.ts` line 252 uses `severity: 'warn'` for a **QR generation crash** — this is an error, not a warning. Switch to `'error'`.
- `webhooks.component.ts` line 158 uses `'warn'` for "Failed" — should be `'error'` so it's coloured + iconed like a real failure.

Set consistent dismiss timing on `app.component.html` line 1:

```html
<p-toast position="top-right" [life]="4000" [breakpoints]="{ '640px': { width: '100%', right: '0', left: '0' } }" />
```

### H10. `register.component.ts` has no password-match / strength hint explanation

Register form uses `<p-password>` with `[feedback]="true"` (default) which
shows a strength bar — good — but `login.component.ts` line 39 explicitly
disables feedback (correct there). Register does not mirror confirm-password
nor show an inline explanation of the 8-char minimum until after the user
has touched the field. Add inline hint up-front:

```html
<label class="form-label" for="password">Password</label>
<p-password id="password" formControlName="password" styleClass="w-full"
            [toggleMask]="true" inputStyleClass="w-full"
            autocomplete="new-password" promptLabel="At least 8 characters" />
<small class="text-slate-500">At least 8 characters.</small>
@if (form.controls.password.touched && form.controls.password.invalid) {
  <small class="text-red-500 block">Password must be at least 8 characters.</small>
}
```

---

## 3. Polish items

### P1. Landing hero — add secondary CTA and social proof line

`landing.component.ts` lines 42-66. The form is the primary CTA, but there's
no "See live demo" / "Read docs" secondary action, and no trust line.

```html
<div class="mt-6 flex items-center justify-center gap-4 text-sm text-slate-500">
  <span><i class="pi pi-check-circle text-brand-500"></i> Free forever for 100 links</span>
  <span><i class="pi pi-check-circle text-brand-500"></i> No credit card</span>
  <span><i class="pi pi-check-circle text-brand-500"></i> Open source</span>
</div>
```

### P2. `stat-card` hover affordance

Assuming `stat-card.component.ts` renders a card, nothing in the dashboard
suggests you can click it to drill into *Links* or *Analytics*. Wrap each
`<app-stat-card>` in a `routerLink` or add a `[routerLink]` input so the
first ("Total links") jumps to `/dashboard/links`.

```html
<!-- overview.component.ts template -->
<a routerLink="/dashboard/links" class="block hover:-translate-y-0.5 transition">
  <app-stat-card label="Total links" [value]="s.total_links" icon="pi pi-link" />
</a>
```

### P3. `create.component.ts` submit-on-Enter works but there is no alias preview

Show the full short URL live as the alias is typed so the user sees what
they're creating:

```html
@if (form.controls.custom_alias.value && !form.controls.custom_alias.errors) {
  <small class="text-slate-500">
    Preview: <span class="font-mono text-brand-600">{{ previewHost }}/{{ form.controls.custom_alias.value }}</span>
  </small>
}
```

```ts
readonly previewHost = (environment.publicShortHost || globalThis.location?.origin || '').replace(/\/$/, '');
```

### P4. Tables have no per-row focus ring / keyboard row activation

`list.component.ts` rows contain multiple anchors; arrow-key navigation
through the table is not wired. For now, at least add `tabindex="0"` on the
row and a focus-visible style via styles.scss:

```scss
.p-datatable tbody tr:focus-visible {
  @apply outline outline-2 outline-offset-[-2px] outline-brand-500;
}
```

### P5. Copy button gives no aria feedback

`copy-button.component.ts` sets visual `pi-check` but no `aria-live`. Screen
readers don't announce the copy.

```html
<button type="button" pButton
        [label]="label()"
        [icon]="copied() ? 'pi pi-check' : 'pi pi-copy'"
        [attr.aria-label]="copied() ? 'Copied' : 'Copy ' + label()"
        [attr.aria-live]="copied() ? 'polite' : null"
        class="p-button-sm p-button-outlined"
        (click)="copy()" [disabled]="!value()">
</button>
```

### P6. `short-date` pipe — no relative time for recent dates

Rows like "Last click" / "Created" all show ISO-ish date. For links
clicked minutes ago, "2 min ago" is more scanable. Optional — extend
`ShortDatePipe` or add a `RelativeDatePipe`.

### P7. Brand colour — one shade only

`tailwind.config.js` defines `brand-50…900` but the UI only uses `brand-600`
(buttons), `brand-700` (hover), `brand-50` (active nav row bg). The palette
is under-used: for example the landing hero is pure white → slate and feels
un-branded. Add a subtle brand tint to the landing hero bg:

```html
<section class="flex-1 flex items-center justify-center px-6 py-16
                bg-gradient-to-b from-brand-50/50 via-white to-slate-50">
```

### P8. `settings.component.ts` profile form loads initial values in constructor only

Lines 82-87 read `this.user()?.full_name` once at construction. If the user
updates elsewhere, the form does not refresh. Convert to `effect`:

```ts
constructor() {
  effect(() => {
    const u = this.user();
    if (!u) return;
    this.profileForm.patchValue({ name: u.full_name ?? '', email: u.email }, { emitEvent: false });
  });
}
```

### P9. `api-keys.component.ts` dialog — pressing Enter in name field does not submit

The dialog uses a plain `<input>` inside a `<div>`, not a `<form>`. Wrap it:

```html
<form (ngSubmit)="create()">
  <div class="flex flex-col gap-3"> ... </div>
  <button type="submit" ... />
</form>
```

### P10. Missing `<title>` updates per route

No use of `Title` service anywhere. Browser tab always says the app name.
Add a `titleResolver` in `app.routes.ts`:

```ts
{ path: 'dashboard/links', component: LinksListComponent, title: 'Links · URL Shortener' },
```

### P11. `webhooks.component.ts` event toggle buttons have no `aria-pressed`

Lines 46-54 — the toggle buttons visually change background but don't
announce state. Add:

```html
<button type="button" class="btn-ghost !px-2 !py-1 text-xs border"
        [attr.aria-pressed]="events().includes(e)"
        ... (click)="toggleEvent(e)">{{ e }}</button>
```

### P12. Focus-visible styles

`styles.scss` line 22 adds `focus-visible:outline` to `.btn-primary` only.
`.btn-ghost` (line 25) has no focus-visible ring. Fix:

```scss
.btn-ghost {
  @apply inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium
         text-slate-700 hover:bg-slate-100
         focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
         focus-visible:outline-brand-600;
}
```

### P13. No skeleton on `links/list.component.ts` initial load

The PrimeNG table shows its internal spinner via `[loading]="store.loading()"`,
but no row-shaped skeletons while fetching first page. Consider `<p-skeleton>`
rows for nicer perceived performance. Optional.

### P14. `.page-title` is used everywhere — good — but has no `id` for landmarking

Add a landmark so screen readers can jump:

```scss
.page-title {
  @apply text-2xl font-semibold text-slate-900;
}
```

and in each template:

```html
<h1 class="page-title" id="page-title" tabindex="-1">Links</h1>
```

Plus add a "skip to content" link in `main-layout.component.html`:

```html
<a href="#page-title" class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2
                             focus:z-50 btn-primary">Skip to content</a>
```

### P15. Typography — body text is default Tailwind

No `fontFamily` configured in `tailwind.config.js`. The PrimeNG Aura preset
pulls its own font. Pick one (e.g. Inter) and set it in `tailwind.config.js`:

```js
theme: {
  extend: {
    fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
    colors: { brand: { /* ... */ } },
  },
},
```

and add `<link href="https://rsms.me/inter/inter.css" rel="stylesheet">` or
self-host via `@fontsource/inter`.

---

## Appendix — Files Touched

| Area                          | File (abs. path)                                                                                          |
|-------------------------------|-----------------------------------------------------------------------------------------------------------|
| Dashboard                     | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\dashboard\overview.component.ts      |
| Links list                    | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\links\list.component.ts              |
| Links create                  | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\links\create.component.ts            |
| Links detail                  | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\links\detail.component.ts            |
| Auth login                    | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\auth\login.component.ts              |
| Auth register                 | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\auth\register.component.ts           |
| Landing                       | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\landing\landing.component.ts         |
| Settings                      | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\settings\settings.component.ts       |
| API keys                      | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\api-keys\api-keys.component.ts       |
| Domains                       | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\domains\domains.component.ts         |
| Webhooks                      | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\features\webhooks\webhooks.component.ts       |
| Main layout                   | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\core\layout\main-layout.component.{ts,html}   |
| Styles                        | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\styles.scss                                       |
| Tailwind config               | C:\Users\User\Desktop\work\url-shortener\admin-panel\tailwind.config.js                                    |
| Copy button (shared)          | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\shared\components\copy-button\copy-button.component.ts |
| App root (toast config)       | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\app.component.html                            |
| Routes (titles)               | C:\Users\User\Desktop\work\url-shortener\admin-panel\src\app\app.routes.ts                                 |
