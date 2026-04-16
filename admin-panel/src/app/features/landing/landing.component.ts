import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { TranslateModule } from '@ngx-translate/core';
import { UrlsApi } from '../../core/api/urls.api';
import { AuthService } from '../../core/auth/auth.service';
import { CopyButtonComponent } from '../../shared/components/copy-button/copy-button.component';

/**
 * Public landing.
 *
 * Design choice: anonymous visitors get a usable "shorten a URL" form, not a
 * redirect to /login. This lets the SPA double as the public front page of
 * the shortener service. Authenticated users still see the same page but
 * with a "Go to dashboard" CTA in the header.
 */
@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [FormsModule, RouterLink, ButtonModule, InputTextModule, CopyButtonComponent, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="min-h-screen flex flex-col">
      <header class="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-white">
        <div class="flex items-center gap-2 font-semibold">
          <span class="inline-flex items-center justify-center w-8 h-8 rounded-md bg-brand-600 text-white">
            <i class="pi pi-link text-sm"></i>
          </span>
          URL Shortener
        </div>
        <nav class="flex items-center gap-2">
          @if (auth.isAuthenticated()) {
            <a routerLink="/dashboard" class="btn-primary">{{ 'nav.overview' | translate }}</a>
          } @else {
            <a routerLink="/login" class="btn-ghost">{{ 'auth.sign_in' | translate }}</a>
            <a routerLink="/register" class="btn-primary">{{ 'auth.create_account' | translate }}</a>
          }
        </nav>
      </header>

      <section class="flex-1 flex items-center justify-center px-6 py-16 bg-gradient-to-b from-white to-slate-50">
        <div class="w-full max-w-2xl text-center">
          <h1 class="text-4xl sm:text-5xl font-bold tracking-tight text-slate-900">
            Shorten any URL. Track every click.
          </h1>
          <p class="mt-4 text-slate-600 text-lg">
            Paste a link and get a short URL instantly. Create an account for analytics,
            custom domains, QR codes, and API access.
          </p>

          <form (ngSubmit)="shorten()" class="mt-10 flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              name="longUrl"
              [ngModel]="longUrl()"
              (ngModelChange)="longUrl.set($event)"
              pInputText
              autofocus
              autocomplete="url"
              aria-label="Long URL to shorten"
              class="flex-1 !text-base !py-3"
              placeholder="https://example.com/long/path/goes/here"
              required />
            <button pButton type="submit" class="!py-3 !px-6"
                    [disabled]="busy() || !longUrl().trim()"
                    [label]="busy() ? 'Shortening…' : 'Shorten'">
            </button>
          </form>

          @if (error()) {
            <div class="mt-3 text-sm text-red-600">{{ error() }}</div>
          }

          @if (result(); as r) {
            <div class="mt-8 card text-left">
              <div class="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Your short URL</div>
              <div class="flex items-center gap-2 flex-wrap">
                <a [href]="r.short_url" target="_blank" rel="noopener"
                   class="text-brand-600 font-mono text-lg break-all hover:underline">{{ r.short_url }}</a>
                <app-copy-button [value]="r.short_url" />
              </div>
              <div class="mt-2 text-xs text-slate-500">
                Want to manage your links, set expiry, or see analytics?
                <a routerLink="/register" class="text-brand-600 hover:underline">Create an account →</a>
              </div>
            </div>
          }
        </div>
      </section>

      <footer class="text-center text-xs text-slate-500 py-6 border-t border-slate-200 bg-white">
        © 2026 URL Shortener · MIT License
      </footer>
    </div>
  `,
})
export class LandingComponent {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(UrlsApi);
  private readonly destroyRef = inject(DestroyRef);

  readonly longUrl = signal('');
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<{ short_code: string; short_url: string } | null>(null);

  shorten(): void {
    if (this.busy()) return;
    let url = this.longUrl().trim();
    if (!url) return;
    // Auto-prefix https:// so users can paste `example.com`.
    if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
    try {
      new URL(url);
    } catch {
      this.error.set('That does not look like a valid URL.');
      return;
    }
    this.longUrl.set(url);
    this.error.set(null);
    this.busy.set(true);
    this.result.set(null);
    this.api
      .shortenPublic(url)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (r) => {
          this.result.set(r);
          this.busy.set(false);
        },
        error: (e: { error?: { error?: { message?: string } }; message?: string }) => {
          this.error.set(e?.error?.error?.message ?? e?.message ?? 'Failed to shorten URL.');
          this.busy.set(false);
        },
      });
  }
}
