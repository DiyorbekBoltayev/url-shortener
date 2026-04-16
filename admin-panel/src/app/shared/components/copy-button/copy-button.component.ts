import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-copy-button',
  standalone: true,
  imports: [ButtonModule, TooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      type="button"
      pButton
      [label]="label()"
      [icon]="copied() ? 'pi pi-check' : 'pi pi-copy'"
      class="p-button-sm p-button-outlined"
      [pTooltip]="tooltipText()"
      tooltipPosition="top"
      [attr.aria-label]="copied() ? 'Copied' : 'Copy ' + label()"
      [attr.aria-live]="copied() ? 'polite' : null"
      (click)="copy()"
      [disabled]="!value()">
    </button>
  `,
})
export class CopyButtonComponent {
  readonly value = input.required<string>();
  readonly label = input<string>('Copy');

  private readonly toast = inject(MessageService, { optional: true });
  readonly copied = signal(false);
  readonly tooltipText = computed(() => (this.copied() ? 'Copied!' : 'Copy to clipboard'));

  async copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.value());
      this.copied.set(true);
      this.toast?.add({ severity: 'success', summary: 'Copied', detail: 'Value copied to clipboard.', life: 1500 });
      // Reset to default tooltip after 1.5s so the next hover shows "Copy to clipboard" again.
      setTimeout(() => this.copied.set(false), 1500);
    } catch {
      this.toast?.add({ severity: 'error', summary: 'Copy failed', detail: 'Clipboard access denied.' });
    }
  }
}
