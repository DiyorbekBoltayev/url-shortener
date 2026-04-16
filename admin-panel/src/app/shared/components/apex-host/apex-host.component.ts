import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { NgApexchartsModule, type ApexOptions } from 'ng-apexcharts';

/**
 * Thin wrapper around ng-apexcharts to keep templates tidy. All options are
 * driven by a single `ApexOptions` input — callers usually derive it via
 * `computed()` so the chart reacts to signal changes.
 *
 * Loaded lazily via `@defer (on viewport)` in consumer pages to keep the
 * initial bundle slim (ApexCharts is ~150 KB gzipped).
 */
@Component({
  selector: 'app-apex-host',
  standalone: true,
  imports: [NgApexchartsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <apx-chart
      [series]="options().series ?? []"
      [chart]="options().chart ?? { type: 'line', height: height() }"
      [xaxis]="options().xaxis ?? {}"
      [yaxis]="options().yaxis ?? {}"
      [stroke]="options().stroke ?? {}"
      [dataLabels]="options().dataLabels ?? { enabled: false }"
      [colors]="options().colors ?? []"
      [fill]="options().fill ?? {}"
      [legend]="options().legend ?? {}"
      [grid]="options().grid ?? {}"
      [tooltip]="options().tooltip ?? {}"
      [labels]="options().labels ?? []"
      [plotOptions]="options().plotOptions ?? {}" />
  `,
})
export class ApexHostComponent {
  readonly options = input.required<ApexOptions>();
  readonly height = input<number>(260);
}
