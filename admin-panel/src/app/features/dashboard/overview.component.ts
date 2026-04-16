import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { TableModule } from 'primeng/table';
import { SkeletonModule } from 'primeng/skeleton';
import { MessageModule } from 'primeng/message';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import type { ApexOptions } from 'ng-apexcharts';
import { AnalyticsApi } from '../../core/api/analytics.api';
import { OverviewStats } from '../../core/models/analytics.model';
import { StatCardComponent } from '../../shared/components/stat-card/stat-card.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ApexHostComponent } from '../../shared/components/apex-host/apex-host.component';

@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [
    RouterLink,
    ButtonModule,
    CardModule,
    TableModule,
    SkeletonModule,
    MessageModule,
    TranslateModule,
    StatCardComponent,
    EmptyStateComponent,
    ApexHostComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <h1 class="page-title">{{ 'overview.title' | translate }}</h1>
    </div>

    @if (loading()) {
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        @for (i of skeletons; track $index) {
          <p-skeleton height="90px" styleClass="!rounded-lg" />
        }
      </div>
      <p-skeleton height="280px" styleClass="!rounded-lg" />
    } @else if (error()) {
      @let e = error() ?? '';
      <p-message severity="error" [text]="e" styleClass="w-full mb-4" />
      <app-empty-state
        icon="pi pi-exclamation-triangle"
        [title]="'overview.no_data' | translate"
        [description]="e">
        <button pButton class="btn-primary mt-4" (click)="load()" [label]="'common.retry' | translate"></button>
      </app-empty-state>
    } @else {
      @if (stats(); as s) {
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <app-stat-card [label]="'overview.total_links' | translate"      [value]="s.total_links"      icon="pi pi-link" />
          <app-stat-card [label]="'overview.total_clicks' | translate"     [value]="s.total_clicks"     icon="pi pi-chart-line" />
          <app-stat-card [label]="'overview.clicks_this_week' | translate" [value]="s.clicks_this_week" icon="pi pi-calendar" />
          <app-stat-card [label]="'overview.active_links' | translate"     [value]="s.active_links"     icon="pi pi-check-circle" />
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <div class="card lg:col-span-2">
            <div class="flex items-center justify-between mb-3">
              <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">{{ 'overview.clicks_7d' | translate }}</h2>
              <span class="text-xs text-slate-500">{{ s.clicks_this_week }} {{ 'common.clicks' | translate }}</span>
            </div>
            @if (hasSeries()) {
              @defer (on viewport) {
                <app-apex-host [options]="chartOpts()" [height]="260" />
              } @placeholder {
                <div class="h-64 animate-pulse bg-slate-100 dark:bg-slate-700 rounded-md"></div>
              }
            } @else {
              <div class="h-64 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">
                <div class="text-center">
                  <i class="pi pi-chart-line text-3xl mb-2"></i>
                  <div>{{ 'overview.no_clicks_yet' | translate }}</div>
                  <a routerLink="/dashboard/links" class="text-brand-600 text-xs hover:underline">{{ 'overview.share_to_get_clicks' | translate }}</a>
                </div>
              </div>
            }
          </div>

          <div class="card">
            <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">{{ 'overview.top_referrers' | translate }}</h2>
            @if ((s.top_referrers ?? []).length > 0) {
              <ul class="divide-y divide-slate-100 dark:divide-slate-700">
                @for (r of s.top_referrers ?? []; track r.referer) {
                  <li class="flex items-center justify-between py-2">
                    <span class="text-sm text-slate-700 dark:text-slate-300 truncate max-w-[70%]">{{ r.referer || '(direct)' }}</span>
                    <span class="text-sm font-medium text-slate-900 dark:text-slate-100">{{ r.clicks }}</span>
                  </li>
                }
              </ul>
            } @else {
              <p class="text-sm text-slate-500 dark:text-slate-400">{{ 'overview.no_referrers' | translate }}</p>
            }
          </div>
        </div>

        @if ((s.top_links ?? []).length > 0) {
          <div class="card">
            <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">{{ 'overview.top_links' | translate }}</h2>
            <ul class="divide-y divide-slate-100 dark:divide-slate-700">
              @for (l of s.top_links ?? []; track l.id) {
                <li class="flex items-center justify-between py-2 gap-3">
                  <a [routerLink]="['/dashboard/links', l.id]"
                     class="flex-1 min-w-0 group">
                    <div class="text-sm font-medium text-slate-900 dark:text-slate-100 truncate group-hover:text-brand-600">
                      {{ l.title || l.short_code }}
                    </div>
                    <div class="text-xs text-slate-500 dark:text-slate-400 truncate">/{{ l.short_code }} → {{ l.long_url }}</div>
                  </a>
                  <span class="text-sm font-semibold text-slate-900 dark:text-slate-100 whitespace-nowrap">{{ l.clicks }} {{ 'common.clicks' | translate }}</span>
                </li>
              }
            </ul>
          </div>
        }
      } @else {
        <app-empty-state
          icon="pi pi-chart-bar"
          [title]="'overview.no_data' | translate"
          [description]="'overview.create_first_link' | translate">
          <a routerLink="/dashboard/links/new" class="btn-primary mt-4">{{ 'links.new_link' | translate }}</a>
        </app-empty-state>
      }
    }
  `,
})
export class OverviewComponent {
  private readonly analytics = inject(AnalyticsApi);
  private readonly destroyRef = inject(DestroyRef);
  private readonly translate = inject(TranslateService);

  readonly skeletons = [1, 2, 3, 4];
  readonly loading = signal(true);
  readonly stats = signal<OverviewStats | null>(null);
  readonly error = signal<string | null>(null);

  readonly hasSeries = computed(() => (this.stats()?.weekly_timeseries ?? []).length > 0);

  readonly chartOpts = computed<ApexOptions>(() => {
    const points = this.stats()?.weekly_timeseries ?? [];
    return {
      chart: { type: 'area', height: 260, toolbar: { show: false }, animations: { enabled: true } },
      stroke: { curve: 'smooth', width: 2 },
      dataLabels: { enabled: false },
      xaxis: { type: 'datetime', labels: { style: { colors: '#64748b' } } },
      yaxis: { labels: { style: { colors: '#64748b' } } },
      tooltip: { theme: 'light', x: { format: 'dd MMM' } },
      grid: { borderColor: '#e2e8f0', strokeDashArray: 3 },
      series: [
        {
          name: 'Clicks',
          data: points.map((p) => [new Date(p.t).getTime(), p.clicks] as [number, number]),
        },
      ],
      colors: ['#2563eb'],
      fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0.05 } },
    };
  });

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.analytics
      .overview()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => {
          this.stats.set(s);
          this.loading.set(false);
        },
        error: (e: { message?: string }) => {
          this.error.set(e?.message ?? this.translate.instant('overview.no_data'));
          this.loading.set(false);
        },
      });
  }
}
