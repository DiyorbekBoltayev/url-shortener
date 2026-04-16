import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { CheckboxModule } from 'primeng/checkbox';
import { DialogModule } from 'primeng/dialog';
import { ConfirmationService, MessageService } from 'primeng/api';
import { firstValueFrom } from 'rxjs';
import { ApiKeysApi } from '../../core/api/api-keys.api';
import { ApiKeyDto } from '../../core/models/url.model';
import { CopyButtonComponent } from '../../shared/components/copy-button/copy-button.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ShortDatePipe } from '../../shared/pipes/short-date.pipe';

const SCOPES = ['urls:read', 'urls:write', 'analytics:read', 'domains:write', 'webhooks:write'] as const;

@Component({
  selector: 'app-api-keys',
  standalone: true,
  imports: [
    FormsModule,
    TableModule,
    ButtonModule,
    InputTextModule,
    CheckboxModule,
    DialogModule,
    CopyButtonComponent,
    EmptyStateComponent,
    ShortDatePipe,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <h1 class="page-title">API keys</h1>
      <button pButton class="btn-primary" (click)="openCreate()">
        <i class="pi pi-plus"></i><span>New key</span>
      </button>
    </div>

    <div class="card">
      <p-table [value]="items()" [loading]="loading()" dataKey="id">
        <ng-template pTemplate="header">
          <tr>
            <th>Name</th>
            <th>Prefix</th>
            <th>Scopes</th>
            <th>Last used</th>
            <th>Created</th>
            <th class="text-right">Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-k>
          <tr>
            <td>{{ k.name }}</td>
            <td class="font-mono text-xs">{{ k.key_prefix }}…</td>
            <td class="text-xs text-slate-600">{{ k.scopes.join(', ') }}</td>
            <td class="text-sm text-slate-500">{{ k.last_used_at ? (k.last_used_at | shortDate) : 'never' }}</td>
            <td class="text-sm text-slate-500">{{ k.created_at | shortDate }}</td>
            <td class="text-right">
              <button pButton class="p-button-sm p-button-text p-button-danger"
                      icon="pi pi-trash" (click)="revoke(k)" aria-label="Revoke"></button>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr>
            <td colspan="6" class="!p-0">
              @if (!loading()) {
                <app-empty-state icon="pi pi-key" title="No API keys"
                                 description="Generate a key to use the HTTP API." />
              }
            </td>
          </tr>
        </ng-template>
      </p-table>
    </div>

    <!-- Create dialog -->
    <p-dialog header="New API key" [modal]="true" [(visible)]="createVisible" [style]="{ width: '480px' }"
              [closable]="!created()">
      @if (!created()) {
        <div class="flex flex-col gap-3">
          <div>
            <label class="form-label" for="keyname">Name</label>
            <input pInputText id="keyname" class="w-full"
                   [ngModel]="name()" (ngModelChange)="name.set($event)"
                   placeholder="CI, webhook…" />
          </div>
          <div>
            <label class="form-label">Scopes</label>
            <div class="grid grid-cols-2 gap-2">
              @for (s of allScopes; track s) {
                <label class="flex items-center gap-2 text-sm">
                  <p-checkbox [binary]="true" [ngModel]="scopes().includes(s)"
                              (ngModelChange)="toggleScope(s, $event)" />
                  {{ s }}
                </label>
              }
            </div>
          </div>
          <div class="flex justify-end gap-2 mt-2">
            <button pButton class="btn-ghost" (click)="createVisible = false" label="Cancel"></button>
            <button pButton class="btn-primary"
                    [disabled]="!name().trim() || scopes().length === 0 || busy()"
                    [label]="busy() ? 'Creating…' : 'Create'"
                    (click)="create()"></button>
          </div>
        </div>
      } @else {
        <div class="flex flex-col gap-3">
          <p class="text-sm text-red-600 font-medium">
            This token is shown only once. Copy it now and store it securely.
          </p>
          <div class="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-md p-2">
            <code class="text-xs break-all flex-1">{{ created()?.key }}</code>
            <app-copy-button [value]="created()?.key ?? ''" />
          </div>
          <div class="flex justify-end">
            <button pButton class="btn-primary" (click)="closeCreated()" label="Done"></button>
          </div>
        </div>
      }
    </p-dialog>
  `,
})
export class ApiKeysComponent implements OnInit {
  private readonly api = inject(ApiKeysApi);
  private readonly toast = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);

  readonly items = signal<ApiKeyDto[]>([]);
  readonly loading = signal(false);
  readonly busy = signal(false);

  protected createVisible = false;
  readonly name = signal('');
  readonly scopes = signal<string[]>(['urls:read', 'urls:write']);
  readonly created = signal<ApiKeyDto | null>(null);
  readonly allScopes = [...SCOPES];

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

  openCreate(): void {
    this.name.set('');
    this.scopes.set(['urls:read', 'urls:write']);
    this.created.set(null);
    this.createVisible = true;
  }

  toggleScope(s: string, on: boolean): void {
    this.scopes.update((l) => (on ? Array.from(new Set([...l, s])) : l.filter((x) => x !== s)));
  }

  async create(): Promise<void> {
    this.busy.set(true);
    try {
      const k = await firstValueFrom(this.api.create({ name: this.name().trim(), scopes: this.scopes() }));
      this.items.update((l) => [k, ...l]);
      this.created.set(k);
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Create failed', detail: (e as Error).message });
    } finally {
      this.busy.set(false);
    }
  }

  closeCreated(): void {
    this.created.set(null);
    this.createVisible = false;
  }

  revoke(k: ApiKeyDto): void {
    this.confirm.confirm({
      header: 'Revoke key?',
      message: `Revoke "${k.name}"? Any client using it will stop working.`,
      icon: 'pi pi-exclamation-triangle',
      acceptButtonStyleClass: 'p-button-danger',
      accept: async () => {
        try {
          await firstValueFrom(this.api.revoke(k.id));
          this.items.update((l) => l.filter((x) => x.id !== k.id));
          this.toast.add({ severity: 'success', summary: 'Revoked' });
        } catch (e) {
          this.toast.add({ severity: 'error', summary: 'Revoke failed', detail: (e as Error).message });
        }
      },
    });
  }
}
