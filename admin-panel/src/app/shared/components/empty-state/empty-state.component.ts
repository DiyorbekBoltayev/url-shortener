import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex flex-col items-center justify-center py-16 text-center">
      <div class="inline-flex items-center justify-center w-14 h-14 rounded-full bg-slate-100 text-slate-500 mb-4">
        <i [class]="icon()" class="text-xl"></i>
      </div>
      <h3 class="text-base font-semibold text-slate-900">{{ title() }}</h3>
      @if (description()) {
        <p class="mt-1 text-sm text-slate-500 max-w-md">{{ description() }}</p>
      }
      <ng-content />
    </div>
  `,
})
export class EmptyStateComponent {
  readonly icon = input<string>('pi pi-inbox');
  readonly title = input.required<string>();
  readonly description = input<string | null>(null);
}
