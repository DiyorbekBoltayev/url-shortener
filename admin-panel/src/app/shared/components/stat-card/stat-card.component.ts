import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-stat-card',
  standalone: true,
  imports: [],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="card flex items-start gap-4">
      <div class="inline-flex items-center justify-center w-10 h-10 rounded-md bg-brand-50 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300 shrink-0">
        <i [class]="icon()"></i>
      </div>
      <div class="flex-1 min-w-0">
        <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">{{ label() }}</div>
        <div class="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-50">{{ value() }}</div>
        @if (hint()) {
          <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">{{ hint() }}</div>
        }
      </div>
    </div>
  `,
})
export class StatCardComponent {
  readonly label = input.required<string>();
  readonly value = input.required<string | number>();
  readonly icon = input<string>('pi pi-chart-bar');
  readonly hint = input<string | null>(null);
}
