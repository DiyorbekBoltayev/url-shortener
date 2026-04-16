import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { TagModule } from 'primeng/tag';
import { ConfirmationService, MessageService } from 'primeng/api';
import { firstValueFrom } from 'rxjs';
import { DomainsApi } from '../../core/api/domains.api';
import { DomainDto } from '../../core/models/url.model';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ShortDatePipe } from '../../shared/pipes/short-date.pipe';

@Component({
  selector: 'app-domains',
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
      <h1 class="page-title">Custom domains</h1>
    </div>

    <div class="card mb-4">
      <h2 class="text-sm font-semibold text-slate-700 mb-3">Add a domain</h2>
      <div class="flex flex-wrap gap-2">
        <label for="newDomain" class="sr-only">Domain</label>
        <input
          pInputText
          id="newDomain"
          class="flex-1 min-w-[240px]"
          aria-label="Custom domain hostname"
          placeholder="links.example.com"
          [ngModel]="newHost()"
          (ngModelChange)="newHost.set($event)" />
        <button pButton class="btn-primary" [disabled]="!newHost().trim() || busy()" (click)="add()">
          <i class="pi pi-plus"></i><span>Add</span>
        </button>
      </div>
      <p class="text-xs text-slate-500 mt-2">
        After adding, point a CNAME from this host to <span class="font-mono">cname.urlshortener.app</span> and click Verify.
      </p>
    </div>

    <div class="card">
      <p-table [value]="items()" [loading]="loading()" dataKey="id">
        <ng-template pTemplate="header">
          <tr>
            <th>Domain</th>
            <th>Status</th>
            <th>SSL</th>
            <th>Verified</th>
            <th>Created</th>
            <th class="text-right">Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-d>
          <tr>
            <td class="font-mono">{{ d.domain }}</td>
            <td>
              @if (d.is_verified) { <p-tag severity="success" value="verified" /> }
              @else                { <p-tag severity="warn"    value="pending"  /> }
            </td>
            <td class="text-xs text-slate-500">{{ d.ssl_status || '—' }}</td>
            <td class="text-sm text-slate-500">{{ d.verified_at ? (d.verified_at | shortDate) : '—' }}</td>
            <td class="text-sm text-slate-500">{{ d.created_at | shortDate }}</td>
            <td class="text-right">
              @if (!d.is_verified) {
                <button pButton class="p-button-sm p-button-text" (click)="verify(d)" icon="pi pi-refresh"
                        label="Verify"></button>
              }
              <button pButton class="p-button-sm p-button-text p-button-danger" (click)="remove(d)"
                      icon="pi pi-trash" aria-label="Delete"></button>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr>
            <td colspan="6" class="!p-0">
              @if (!loading()) {
                <app-empty-state icon="pi pi-globe" title="No domains"
                                 description="Add a custom domain to brand your short links." />
              }
            </td>
          </tr>
        </ng-template>
      </p-table>
    </div>
  `,
})
export class DomainsComponent implements OnInit {
  private readonly api = inject(DomainsApi);
  private readonly toast = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);

  readonly items = signal<DomainDto[]>([]);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly newHost = signal('');

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

  async add(): Promise<void> {
    const host = this.newHost().trim();
    if (!host) return;
    this.busy.set(true);
    try {
      const d = await firstValueFrom(this.api.create(host));
      this.items.update((l) => [d, ...l]);
      this.newHost.set('');
      this.toast.add({ severity: 'success', summary: 'Domain added', detail: host });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Add failed', detail: (e as Error).message });
    } finally {
      this.busy.set(false);
    }
  }

  async verify(d: DomainDto): Promise<void> {
    try {
      const updated = await firstValueFrom(this.api.verify(d.id));
      this.items.update((l) => l.map((x) => (x.id === d.id ? updated : x)));
      this.toast.add({
        severity: updated.is_verified ? 'success' : 'warn',
        summary: updated.is_verified ? 'Verified' : 'Still pending',
      });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Verify failed', detail: (e as Error).message });
    }
  }

  remove(d: DomainDto): void {
    this.confirm.confirm({
      header: 'Remove domain?',
      message: `Remove ${d.domain}? Existing short links will stop working on it.`,
      icon: 'pi pi-exclamation-triangle',
      acceptButtonStyleClass: 'p-button-danger',
      accept: async () => {
        try {
          await firstValueFrom(this.api.delete(d.id));
          this.items.update((l) => l.filter((x) => x.id !== d.id));
          this.toast.add({ severity: 'success', summary: 'Domain removed' });
        } catch (e) {
          this.toast.add({ severity: 'error', summary: 'Remove failed', detail: (e as Error).message });
        }
      },
    });
  }
}
