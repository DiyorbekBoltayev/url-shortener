import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { TagModule } from 'primeng/tag';
import { SelectButtonModule } from 'primeng/selectbutton';
import { SkeletonModule } from 'primeng/skeleton';
import { MessageModule } from 'primeng/message';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';
import type { ApexOptions } from 'ng-apexcharts';
import QRCode from 'qrcode';
import { environment } from '../../../environments/environment';
import { UrlsApi } from '../../core/api/urls.api';
import { AnalyticsApi } from '../../core/api/analytics.api';
import { UrlDto } from '../../core/models/url.model';
import {
  AnalyticsRange,
  GeoBreakdown,
  ReferrerBreakdown,
  TimeseriesResponse,
} from '../../core/models/analytics.model';
import { CopyButtonComponent } from '../../shared/components/copy-button/copy-button.component';
import { ApexHostComponent } from '../../shared/components/apex-host/apex-host.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ShortDatePipe } from '../../shared/pipes/short-date.pipe';
import { QrDialogComponent } from './qr-dialog.component';
import { RoutingTabComponent } from './routing-tab.component';
import { PixelsTabComponent } from './pixels-tab.component';
import { DrawerModule } from 'primeng/drawer';
import { firstValueFrom } from 'rxjs';
import { RoutingRules } from '../../core/models/url.model';

@Component({
  selector: 'app-link-detail',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    ButtonModule,
    CardModule,
    TagModule,
    SelectButtonModule,
    SkeletonModule,
    MessageModule,
    TranslateModule,
    CopyButtonComponent,
    ApexHostComponent,
    EmptyStateComponent,
    ShortDatePipe,
    QrDialogComponent,
    RoutingTabComponent,
    PixelsTabComponent,
    DrawerModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <a routerLink="/dashboard/links" class="btn-ghost">
          <i class="pi pi-arrow-left"></i>
        </a>
        <h1 class="page-title">Link detail</h1>
      </div>
      @if (link(); as l) {
        <div class="flex items-center gap-2">
          @if (l.is_active) {
            <p-tag severity="success" [value]="'links.active' | translate" />
          } @else {
            <p-tag severity="danger" [value]="'links.disabled' | translate" />
          }
          <button pButton type="button" class="btn-ghost"
                  (click)="editDrawerOpen.set(true)">
            <i class="pi pi-cog"></i><span>{{ 'common.edit' | translate }}</span>
          </button>
        </div>
      }
    </div>

    @if (link(); as l) {
      @if (l.safety_status === 'warn') {
        <div class="mb-4 flex items-center gap-3 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-900/30 p-3 text-amber-800 dark:text-amber-200">
          <i class="pi pi-exclamation-triangle"></i>
          <div class="flex-1">
            <div class="font-semibold text-sm">{{ 'links.safety_warning' | translate }}</div>
            <div class="text-xs">{{ l.safety_reason || ('links.needs_review' | translate) }}</div>
          </div>
          <button pButton class="p-button-sm" label="Review" (click)="editDrawerOpen.set(true)"></button>
        </div>
      } @else if (l.safety_status === 'block') {
        <div class="mb-4 flex items-center gap-3 rounded-md border border-red-300 bg-red-50 dark:bg-red-900/30 p-3 text-red-800 dark:text-red-200">
          <i class="pi pi-ban"></i>
          <div>
            <div class="font-semibold text-sm">{{ 'links.link_disabled' | translate }}</div>
            <div class="text-xs">This link is disabled due to safety concerns: {{ l.safety_reason || 'policy violation.' }}</div>
          </div>
        </div>
      } @else if (l.safety_status === 'unchecked') {
        <div class="mb-4">
          <p-tag value="safety: pending" severity="secondary" />
        </div>
      }
    }

    @if (loading()) {
      <p-skeleton height="120px" styleClass="!rounded-lg mb-4" />
      <p-skeleton height="280px" styleClass="!rounded-lg" />
    } @else if (loadError()) {
      @let err = loadError() ?? '';
      <p-message severity="error" [text]="err" styleClass="w-full mb-4" />
      <app-empty-state
        icon="pi pi-exclamation-triangle"
        title="Couldn't load link"
        [description]="err">
        <button pButton class="btn-primary mt-4" (click)="reload()" label="Retry"></button>
      </app-empty-state>
    } @else {
      @if (link(); as l) {
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div class="card lg:col-span-2">
          <div class="text-xs uppercase tracking-wide text-slate-500 mb-1">{{ 'links.short_url' | translate }}</div>
          <div class="flex items-center gap-2 flex-wrap mb-3">
            <a [href]="shortUrl()" target="_blank" rel="noopener"
               class="font-mono text-brand-600 text-lg break-all hover:underline">{{ shortUrl() }}</a>
            <app-copy-button [value]="shortUrl()" />
          </div>
          <div class="text-xs uppercase tracking-wide text-slate-500 mb-1">{{ 'links.destination' | translate }}</div>
          <a [href]="l.long_url" target="_blank" rel="noopener"
             class="text-slate-700 break-all hover:underline">{{ l.long_url }}</a>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
            <div>
              <div class="text-xs text-slate-500">{{ 'common.clicks' | translate }}</div>
              <div class="text-lg font-semibold">{{ l.click_count }}</div>
            </div>
            <div>
              <div class="text-xs text-slate-500">{{ 'links.created' | translate }}</div>
              <div class="text-sm">{{ l.created_at | shortDate }}</div>
            </div>
            <div>
              <div class="text-xs text-slate-500">{{ 'links.expires' | translate }}</div>
              <div class="text-sm">{{ l.expires_at ? (l.expires_at | shortDate) : '—' }}</div>
            </div>
            <div>
              <div class="text-xs text-slate-500">{{ 'links.last_click' | translate }}</div>
              <div class="text-sm">{{ l.last_clicked_at ? (l.last_clicked_at | shortDate) : '—' }}</div>
            </div>
          </div>
        </div>

        <div class="card flex flex-col items-center">
          <div class="text-xs uppercase tracking-wide text-slate-500 mb-2 self-start w-full flex items-center justify-between">
            <span>{{ 'links.qr_code' | translate }}</span>
            <button type="button" class="btn-ghost" (click)="toggleQrEditor()">
              <i class="pi pi-sliders-h"></i>
              <span>{{ qrEditorOpen() ? ('links.hide' | translate) : ('links.customize' | translate) }}</span>
            </button>
          </div>
          @if (qrDataUrl(); as qr) {
            <img [src]="qr" alt="QR code" class="w-48 h-48" />
            <a [href]="qr" [download]="l.short_code + '.png'"
               class="btn-ghost mt-3">
              <i class="pi pi-download"></i><span>{{ 'links.download_png' | translate }}</span>
            </a>
          } @else {
            <p-skeleton width="192px" height="192px" />
          }
        </div>
      </div>

      @if (qrEditorOpen()) {
        <div class="mb-6">
          <app-qr-dialog [link]="l" (styleSaved)="onQrStyleSaved($event)" />
        </div>
      }

      @if (l.og_title || l.og_description || l.og_image_url) {
        <div class="card mb-4">
          <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">{{ 'links.preview' | translate }}</h2>
          <div class="flex items-start gap-3 border rounded overflow-hidden max-w-xl">
            @if (l.og_image_url) {
              <img [src]="l.og_image_url" alt=""
                   class="w-32 h-32 object-cover shrink-0" loading="lazy" />
            }
            <div class="flex flex-col p-3 min-w-0">
              @if (l.favicon_url) {
                <img [src]="l.favicon_url" alt="" class="w-4 h-4 mb-1" loading="lazy" />
              }
              <div class="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                {{ l.og_title ?? l.long_url }}
              </div>
              @if (l.og_description) {
                <div class="text-xs text-slate-500 line-clamp-2">{{ l.og_description }}</div>
              }
              <div class="text-[11px] text-slate-400 mt-1 truncate">{{ l.long_url }}</div>
            </div>
          </div>
        </div>
      }

      @if (l.safety_status === 'block') {
        <app-empty-state icon="pi pi-ban"
                         [title]="'links.analytics_hidden' | translate"
                         description="This link is disabled due to safety concerns; analytics are not available." />
      } @else {
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-slate-700">Clicks over time</h2>
          <p-selectButton
            [options]="ranges"
            optionValue="value"
            optionLabel="label"
            [ngModel]="range()"
            (ngModelChange)="changeRange($event)" />
        </div>
        @defer (on viewport) {
          <app-apex-host [options]="chartOpts()" [height]="260" />
        } @placeholder {
          <div class="h-64 animate-pulse bg-slate-100 rounded-md"></div>
        }
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        <div class="card">
          <h2 class="text-sm font-semibold text-slate-700 mb-3">Top countries</h2>
          @if (geo().length > 0) {
            <ul class="divide-y divide-slate-100">
              @for (g of geo(); track g.country_code) {
                <li class="flex items-center justify-between py-2">
                  <span class="text-sm text-slate-700">{{ g.country }}</span>
                  <span class="text-sm font-medium">{{ g.clicks }}</span>
                </li>
              }
            </ul>
          } @else {
            <p class="text-sm text-slate-500">No data yet.</p>
          }
        </div>
        <div class="card">
          <h2 class="text-sm font-semibold text-slate-700 mb-3">Top referrers</h2>
          @if (referrers().length > 0) {
            <ul class="divide-y divide-slate-100">
              @for (r of referrers(); track r.referer) {
                <li class="flex items-center justify-between py-2">
                  <span class="text-sm text-slate-700 truncate max-w-[70%]">{{ r.referer || '(direct)' }}</span>
                  <span class="text-sm font-medium">{{ r.clicks }}</span>
                </li>
              }
            </ul>
          } @else {
            <p class="text-sm text-slate-500">No data yet.</p>
          }
        </div>
      </div>
      }

      <!-- Routing & Pixels drawer -->
      <p-drawer
        [visible]="editDrawerOpen()"
        (visibleChange)="editDrawerOpen.set($event)"
        position="right"
        [style]="{ width: '560px' }"
        header="Edit link">
        <div class="flex flex-col gap-6">
          <section>
            <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">Routing rules</h3>
            <app-routing-tab [ngModel]="routingDraft()"
                             (ngModelChange)="routingDraft.set($event)" />
            <div class="flex items-center gap-2 mt-3">
              <button pButton class="btn-primary" [disabled]="savingRouting()"
                      [label]="savingRouting() ? 'Saving…' : 'Save routing'"
                      (click)="saveRouting()"></button>
            </div>
          </section>

          <section>
            <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">Tracking pixels</h3>
            <app-pixels-tab [urlId]="l.id" />
          </section>
        </div>
      </p-drawer>
      } @else {
        <app-empty-state
          icon="pi pi-question-circle"
          title="Link not found"
          description="This link may have been deleted or you don't have access.">
          <a routerLink="/dashboard/links" class="btn-primary mt-4">Back to links</a>
        </app-empty-state>
      }
    }
  `,
})
export class LinkDetailComponent implements OnInit {
  // Bound from the :id route segment via withComponentInputBinding()
  readonly id = input.required<string>();

  private readonly urlsApi = inject(UrlsApi);
  private readonly analyticsApi = inject(AnalyticsApi);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly loadError = signal<string | null>(null);
  readonly link = signal<UrlDto | null>(null);
  readonly range = signal<AnalyticsRange>('7d');
  readonly series = signal<TimeseriesResponse | null>(null);
  readonly geo = signal<GeoBreakdown[]>([]);
  readonly referrers = signal<ReferrerBreakdown[]>([]);
  readonly qrDataUrl = signal<string | null>(null);
  readonly qrEditorOpen = signal(false);
  readonly editDrawerOpen = signal(false);
  readonly routingDraft = signal<RoutingRules | null>(null);
  readonly savingRouting = signal(false);

  readonly ranges = [
    { label: '24h', value: '24h' as AnalyticsRange },
    { label: '7d',  value: '7d'  as AnalyticsRange },
    { label: '30d', value: '30d' as AnalyticsRange },
    { label: '90d', value: '90d' as AnalyticsRange },
  ];

  readonly shortUrl = computed(() => {
    const l = this.link();
    if (!l) return '';
    const base = environment.publicShortHost || globalThis.location?.origin || '';
    return `${base.replace(/\/$/, '')}/${l.short_code}`;
  });

  readonly chartOpts = computed<ApexOptions>(() => {
    const points = this.series()?.points ?? [];
    return {
      chart: { type: 'area', height: 260, toolbar: { show: false } },
      stroke: { curve: 'smooth', width: 2 },
      dataLabels: { enabled: false },
      xaxis: { type: 'datetime' },
      series: [
        {
          name: 'Clicks',
          data: points.map((p) => [new Date(p.t).getTime(), p.clicks] as [number, number]),
        },
      ],
      colors: ['#2563eb'],
      fill: { type: 'gradient', gradient: { opacityFrom: 0.45, opacityTo: 0.05 } },
    };
  });

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.urlsApi
      .get(this.id())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (l) => {
          this.link.set(l);
          this.routingDraft.set(l.routing_rules ?? null);
          this.loading.set(false);
          this.renderQr();
        },
        error: (e: { status?: number; message?: string }) => {
          this.loading.set(false);
          // 404 — render the "Link not found" empty state (keep link null, clear error).
          if (e?.status === 404) {
            this.link.set(null);
            return;
          }
          this.loadError.set(e?.message ?? 'Could not load this link.');
        },
      });
    this.loadAnalytics();
  }

  private loadAnalytics(): void {
    const id = this.id();
    const r = this.range();
    this.analyticsApi
      .timeseries(id, r)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => this.series.set(s),
        error: (e: Error) => {
          this.series.set(null);
          this.toast.add({ severity: 'warn', summary: 'Analytics unavailable', detail: e.message });
        },
      });
    this.analyticsApi
      .geo(id, r)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (g) => this.geo.set(g),
        error: () => this.geo.set([]),
      });
    this.analyticsApi
      .referrers(id, r)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (g) => this.referrers.set(g),
        error: () => this.referrers.set([]),
      });
  }

  changeRange(r: AnalyticsRange): void {
    this.range.set(r);
    this.loadAnalytics();
  }

  toggleQrEditor(): void {
    this.qrEditorOpen.update((v) => !v);
  }

  async saveRouting(): Promise<void> {
    const id = this.link()?.id;
    if (!id) return;
    this.savingRouting.set(true);
    try {
      const updated = await firstValueFrom(
        this.urlsApi.update(id, { routing_rules: this.routingDraft() }),
      );
      this.link.set(updated);
      this.toast.add({ severity: 'success', summary: 'Routing saved' });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Save failed', detail: (e as Error).message });
    } finally {
      this.savingRouting.set(false);
    }
  }

  onQrStyleSaved(style: import('../../core/models/url.model').QRStyle): void {
    const l = this.link();
    if (l) this.link.set({ ...l, qr_style: style });
  }

  private async renderQr(): Promise<void> {
    try {
      const dataUrl = await QRCode.toDataURL(this.shortUrl(), { width: 384, margin: 1 });
      this.qrDataUrl.set(dataUrl);
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'QR', detail: (e as Error).message });
    }
  }
}
