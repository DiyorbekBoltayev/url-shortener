import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { TagModule } from 'primeng/tag';
import { ConfirmationService, MessageService } from 'primeng/api';
import { firstValueFrom } from 'rxjs';
import { WebhooksApi } from '../../core/api/webhooks.api';
import { WebhookDto } from '../../core/models/url.model';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ShortDatePipe } from '../../shared/pipes/short-date.pipe';

const EVENTS = ['link.created', 'link.clicked', 'link.expired', 'domain.verified'] as const;

@Component({
  selector: 'app-webhooks',
  standalone: true,
  imports: [
    FormsModule,
    TableModule,
    ButtonModule,
    InputTextModule,
    TagModule,
    EmptyStateComponent,
    ShortDatePipe,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <h1 class="page-title">Webhooks</h1>
    </div>

    <div class="card mb-4">
      <h2 class="text-sm font-semibold text-slate-700 mb-3">Add endpoint</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
        <div class="md:col-span-2">
          <label class="form-label" for="wurl">Endpoint URL</label>
          <input pInputText id="wurl" class="w-full"
                 placeholder="https://hooks.example.com/…"
                 [ngModel]="newUrl()" (ngModelChange)="newUrl.set($event)" />
        </div>
        <div>
          <label class="form-label">Events</label>
          <div class="flex flex-wrap gap-2">
            @for (e of allEvents; track e) {
              <button type="button" class="btn-ghost !px-2 !py-1 text-xs border"
                      [class.bg-brand-50]="events().includes(e)"
                      [class.text-brand-700]="events().includes(e)"
                      [class.border-brand-300]="events().includes(e)"
                      [class.border-slate-200]="!events().includes(e)"
                      (click)="toggleEvent(e)">{{ e }}</button>
            }
          </div>
        </div>
      </div>
      <div class="mt-3">
        <button pButton class="btn-primary"
                [disabled]="!newUrl().trim() || events().length === 0 || busy()"
                (click)="add()">
          <i class="pi pi-plus"></i><span>Add webhook</span>
        </button>
      </div>
    </div>

    <div class="card">
      <p-table [value]="items()" [loading]="loading()" dataKey="id">
        <ng-template pTemplate="header">
          <tr>
            <th>URL</th>
            <th>Events</th>
            <th>Status</th>
            <th>Created</th>
            <th class="text-right">Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-w>
          <tr>
            <td class="font-mono text-xs max-w-md truncate" [title]="w.url">{{ w.url }}</td>
            <td class="text-xs text-slate-600">{{ w.events.join(', ') }}</td>
            <td>
              @if (w.is_active) { <p-tag severity="success" value="active" /> }
              @else             { <p-tag severity="danger"  value="disabled" /> }
            </td>
            <td class="text-sm text-slate-500">{{ w.created_at | shortDate }}</td>
            <td class="text-right">
              <button pButton class="p-button-sm p-button-text" icon="pi pi-send"
                      (click)="test(w)" label="Test"></button>
              <button pButton class="p-button-sm p-button-text p-button-danger" icon="pi pi-trash"
                      (click)="remove(w)" aria-label="Delete"></button>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr>
            <td colspan="5" class="!p-0">
              @if (!loading()) {
                <app-empty-state icon="pi pi-send" title="No webhooks"
                                 description="Receive real-time events when links are created or clicked." />
              }
            </td>
          </tr>
        </ng-template>
      </p-table>
    </div>
  `,
})
export class WebhooksComponent implements OnInit {
  private readonly api = inject(WebhooksApi);
  private readonly toast = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);

  readonly items = signal<WebhookDto[]>([]);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly newUrl = signal('');
  readonly events = signal<string[]>([]);
  readonly allEvents = [...EVENTS];

  ngOnInit(): void {
    void this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const res = await firstValueFrom(this.api.list({ page: 1, per_page: 100 }));
      this.items.set(res.items);
    } finally {
      this.loading.set(false);
    }
  }

  toggleEvent(e: string): void {
    this.events.update((l) => (l.includes(e) ? l.filter((x) => x !== e) : [...l, e]));
  }

  async add(): Promise<void> {
    this.busy.set(true);
    try {
      const w = await firstValueFrom(this.api.create({ url: this.newUrl().trim(), events: this.events() }));
      this.items.update((l) => [w, ...l]);
      this.newUrl.set('');
      this.events.set([]);
      this.toast.add({ severity: 'success', summary: 'Webhook added' });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Add failed', detail: (e as Error).message });
    } finally {
      this.busy.set(false);
    }
  }

  async test(w: WebhookDto): Promise<void> {
    try {
      const res = await firstValueFrom(this.api.test(w.id));
      this.toast.add({
        severity: res.ok ? 'success' : 'error',
        summary: res.ok ? 'Delivered' : 'Failed',
      });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Test failed', detail: (e as Error).message });
    }
  }

  remove(w: WebhookDto): void {
    this.confirm.confirm({
      header: 'Delete webhook?',
      message: 'Stop delivering events to this endpoint?',
      icon: 'pi pi-exclamation-triangle',
      acceptButtonStyleClass: 'p-button-danger',
      accept: async () => {
        try {
          await firstValueFrom(this.api.delete(w.id));
          this.items.update((l) => l.filter((x) => x.id !== w.id));
          this.toast.add({ severity: 'success', summary: 'Deleted' });
        } catch (e) {
          this.toast.add({ severity: 'error', summary: 'Delete failed', detail: (e as Error).message });
        }
      },
    });
  }
}
