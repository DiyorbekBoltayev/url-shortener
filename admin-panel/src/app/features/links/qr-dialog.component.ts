import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { MessageService } from 'primeng/api';
import { Subject, debounceTime } from 'rxjs';
import { UrlsApi, QrPreviewOptions } from '../../core/api/urls.api';
import { QRStyle, UrlDto } from '../../core/models/url.model';

const HEX_RE = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

const DEFAULT_STYLE: Required<Pick<QRStyle, 'fg' | 'bg' | 'frame' | 'dots' | 'corners'>> &
  QRStyle = {
  fg: '#111111',
  bg: '#ffffff',
  frame: 'none',
  dots: 'square',
  corners: 'square',
  logo_url: '',
  eye_color: '',
};

/**
 * Branded-QR editor. Lives inside the link detail page as a side-panel,
 * not a floating modal — that way the live preview has plenty of room.
 *
 * The preview re-fetches `/qr?...` via :meth:`UrlsApi.qrBlob` with a 200ms
 * debounce. "Save as default" persists via POST ``/qr-style``.
 */
@Component({
  selector: 'app-qr-dialog',
  standalone: true,
  imports: [FormsModule, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Branded QR
        </h2>
        <button type="button" class="btn-ghost" (click)="reset()">
          <i class="pi pi-refresh"></i><span>Reset</span>
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Live preview ------------------------------------------------ -->
        <div class="flex flex-col items-center">
          @if (previewSrc(); as src) {
            <img [src]="src" alt="QR preview"
                 class="w-64 h-64 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700" />
          } @else {
            <div class="w-64 h-64 rounded-lg bg-slate-100 dark:bg-slate-800 animate-pulse"></div>
          }

          <div class="flex items-center gap-2 mt-3">
            <button type="button" pButton class="btn-primary"
                    (click)="download('png')">
              <i class="pi pi-download"></i><span>PNG</span>
            </button>
            <button type="button" pButton class="btn-ghost"
                    (click)="download('svg')">
              <i class="pi pi-file"></i><span>SVG</span>
            </button>
          </div>
        </div>

        <!-- Controls ---------------------------------------------------- -->
        <div class="flex flex-col gap-3">
          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Foreground
            </label>
            <div class="flex items-center gap-2">
              <input type="color" [ngModel]="style().fg ?? '#111111'"
                     (ngModelChange)="patch({ fg: $event })"
                     class="h-9 w-12 rounded cursor-pointer border border-slate-300 dark:border-slate-600 bg-transparent" />
              <input type="text" [ngModel]="style().fg ?? ''"
                     (ngModelChange)="patch({ fg: $event })"
                     placeholder="#111"
                     class="flex-1 px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 font-mono" />
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Background
            </label>
            <div class="flex items-center gap-2">
              <input type="color" [ngModel]="style().bg ?? '#ffffff'"
                     (ngModelChange)="patch({ bg: $event })"
                     class="h-9 w-12 rounded cursor-pointer border border-slate-300 dark:border-slate-600 bg-transparent" />
              <input type="text" [ngModel]="style().bg ?? ''"
                     (ngModelChange)="patch({ bg: $event })"
                     placeholder="#fff"
                     class="flex-1 px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 font-mono" />
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Dot style
            </label>
            <select [ngModel]="style().dots ?? 'square'"
                    (ngModelChange)="patch({ dots: $event })"
                    class="w-full px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">
              <option value="square">Square</option>
              <option value="rounded">Rounded</option>
              <option value="extra-rounded">Extra rounded</option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Corner style
            </label>
            <select [ngModel]="style().corners ?? 'square'"
                    (ngModelChange)="patch({ corners: $event })"
                    class="w-full px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">
              <option value="square">Square</option>
              <option value="rounded">Rounded</option>
              <option value="extra-rounded">Extra rounded</option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Frame
            </label>
            <select [ngModel]="style().frame ?? 'none'"
                    (ngModelChange)="patch({ frame: $event })"
                    class="w-full px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">
              <option value="none">None</option>
              <option value="square">Square</option>
              <option value="rounded">Rounded</option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Logo URL
            </label>
            <input type="url" [ngModel]="style().logo_url ?? ''"
                   (ngModelChange)="patch({ logo_url: $event })"
                   placeholder="https://example.com/logo.png"
                   class="w-full px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100" />
            <p class="text-[10px] text-slate-500 mt-1">
              HTTP(S) only, max 512 KB. Skipped silently if too large.
            </p>
          </div>

          <div class="flex items-center gap-2 mt-2">
            <button type="button" pButton class="btn-primary"
                    [disabled]="saving()"
                    (click)="save()">
              <i class="pi pi-save"></i>
              <span>{{ saving() ? 'Saving…' : 'Save as default' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class QrDialogComponent implements OnInit {
  readonly link = input.required<UrlDto>();
  readonly styleSaved = output<QRStyle>();

  private readonly urlsApi = inject(UrlsApi);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly style = signal<QRStyle>({ ...DEFAULT_STYLE });
  readonly saving = signal(false);
  readonly previewSrc = signal<string | null>(null);

  private readonly debouncer$ = new Subject<void>();
  private currentObjectUrl: string | null = null;

  readonly previewOpts = computed<QrPreviewOptions>(() => {
    const s = this.style();
    return {
      size: 320,
      fmt: 'png',
      fg: hexOrUndef(s.fg),
      bg: hexOrUndef(s.bg),
      logo_url: s.logo_url || undefined,
      frame: s.frame ?? undefined,
      dots: s.dots ?? undefined,
      corners: s.corners ?? undefined,
      eye_color: hexOrUndef(s.eye_color),
    };
  });

  constructor() {
    // Re-fetch preview when style changes (debounced 200ms).
    this.debouncer$
      .pipe(debounceTime(200), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.refreshPreview());

    // Kick the debouncer whenever `style` changes.
    effect(() => {
      // read signal to track
      void this.style();
      this.debouncer$.next();
    });
  }

  ngOnInit(): void {
    // Seed from any previously persisted style.
    const saved = this.link().qr_style;
    if (saved && Object.keys(saved).length > 0) {
      this.style.set({ ...DEFAULT_STYLE, ...saved });
    }
    this.refreshPreview();
  }

  patch(partial: Partial<QRStyle>): void {
    this.style.update((s) => ({ ...s, ...partial }));
  }

  reset(): void {
    this.style.set({ ...DEFAULT_STYLE });
  }

  save(): void {
    const s = this.buildSanitized();
    if (!s) return;
    this.saving.set(true);
    this.urlsApi
      .saveQrStyle(this.link().id, s)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.saving.set(false);
          this.toast.add({
            severity: 'success',
            summary: 'QR style saved',
            detail: 'This style will be used on every render of this link.',
          });
          this.styleSaved.emit(res);
        },
        error: (e: Error) => {
          this.saving.set(false);
          this.toast.add({
            severity: 'error',
            summary: 'Save failed',
            detail: e.message,
          });
        },
      });
  }

  download(fmt: 'png' | 'svg'): void {
    this.urlsApi
      .qrBlob(this.link().id, { ...this.previewOpts(), fmt, size: 1024 })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (blob) => {
          const href = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = href;
          a.download = `${this.link().short_code}.${fmt}`;
          a.click();
          URL.revokeObjectURL(href);
        },
        error: (e: Error) =>
          this.toast.add({ severity: 'error', summary: 'Download failed', detail: e.message }),
      });
  }

  private refreshPreview(): void {
    const sanitized = this.buildSanitized({ silent: true });
    if (!sanitized) return;
    this.urlsApi
      .qrBlob(this.link().id, this.previewOpts())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (blob) => {
          if (this.currentObjectUrl) URL.revokeObjectURL(this.currentObjectUrl);
          this.currentObjectUrl = URL.createObjectURL(blob);
          this.previewSrc.set(this.currentObjectUrl);
        },
        error: () => {
          // keep the last good preview on transient render errors
        },
      });
  }

  /** Strip empty strings, coerce to backend shape, warn on invalid hex. */
  private buildSanitized(opts: { silent?: boolean } = {}): QRStyle | null {
    const s = this.style();
    const out: QRStyle = {};
    for (const key of ['fg', 'bg', 'eye_color'] as const) {
      const v = (s[key] ?? '').trim();
      if (!v) continue;
      if (!HEX_RE.test(v)) {
        if (!opts.silent) {
          this.toast.add({
            severity: 'warn',
            summary: 'Invalid colour',
            detail: `"${v}" is not a valid hex colour (use #abc or #aabbcc).`,
          });
        }
        return null;
      }
      out[key] = v;
    }
    if (s.logo_url && s.logo_url.trim()) out.logo_url = s.logo_url.trim();
    if (s.frame && s.frame !== 'none') out.frame = s.frame;
    if (s.dots && s.dots !== 'square') out.dots = s.dots;
    if (s.corners && s.corners !== 'square') out.corners = s.corners;
    return out;
  }
}

function hexOrUndef(v: string | null | undefined): string | undefined {
  if (!v) return undefined;
  return HEX_RE.test(v) ? v : undefined;
}
