import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TableModule, TableLazyLoadEvent } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { TagModule } from 'primeng/tag';
import { CheckboxModule } from 'primeng/checkbox';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { MenuModule } from 'primeng/menu';
import { ConfirmationService, MenuItem, MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';
import { debounceTime, distinctUntilChanged, firstValueFrom, skip } from 'rxjs';
import { environment } from '../../../environments/environment';
import { LinksStore } from './links.store';
import { UrlDto, SafetyStatus } from '../../core/models/url.model';
import { FolderDto } from '../../core/models/folder.model';
import { FoldersApi } from '../../core/api/folders.api';
import { BulkJobsApi } from '../../core/api/bulk-jobs.api';
import { CopyButtonComponent } from '../../shared/components/copy-button/copy-button.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ShortDatePipe } from '../../shared/pipes/short-date.pipe';
import { FoldersTreeComponent } from './folders-tree.component';
import { BulkImportComponent } from './bulk-import.component';

@Component({
  selector: 'app-links-list',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    TableModule,
    ButtonModule,
    InputTextModule,
    TagModule,
    CheckboxModule,
    DialogModule,
    SelectModule,
    MenuModule,
    TranslateModule,
    CopyButtonComponent,
    EmptyStateComponent,
    ShortDatePipe,
    FoldersTreeComponent,
    BulkImportComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <h1 class="page-title">{{ 'links.title' | translate }}</h1>
      <div class="flex items-center gap-2">
        <button pButton class="btn-ghost" (click)="showImport.set(true)">
          <i class="pi pi-upload"></i><span class="hidden sm:inline ml-1">Import CSV</span>
        </button>
        <button pButton class="btn-ghost" [disabled]="exporting()" (click)="exportAll()">
          <i class="pi pi-download"></i><span class="hidden sm:inline ml-1">Export</span>
        </button>
        <a routerLink="/dashboard/links/new" class="btn-primary">
          <i class="pi pi-plus"></i><span>{{ 'links.new_link' | translate }}</span>
        </a>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-4">
      <!-- Folders sidebar -->
      <aside class="card lg:sticky lg:top-0 self-start">
        <app-folders-tree (folderChange)="onFolderChange($event)" />
      </aside>

      <div class="card">
        <div class="flex items-center justify-between mb-4 gap-2 flex-wrap">
          <span class="p-input-icon-left max-w-sm flex-1">
            <i class="pi pi-search"></i>
            <input
              pInputText
              type="text"
              class="w-full"
              aria-label="Search links"
              [placeholder]="'links.search_placeholder' | translate"
              [ngModel]="search()"
              (ngModelChange)="search.set($event)" />
          </span>
          <span class="text-sm text-slate-500">{{ store.total() }} total</span>
        </div>

        @if (selectedIds().length > 0) {
          <div class="flex items-center gap-2 mb-3 p-2 rounded bg-brand-50 dark:bg-brand-900/30">
            <span class="text-sm font-medium">{{ selectedIds().length }} selected</span>
            <button pButton class="p-button-sm" label="Move to folder" (click)="bulkMoveMenu.toggle($event)"></button>
            <button pButton class="p-button-sm" label="Disable" (click)="bulkDisable()"></button>
            <button pButton class="p-button-sm p-button-danger" label="Delete" (click)="bulkDelete()"></button>
            <button pButton class="p-button-text p-button-sm" label="Clear" (click)="selected.set({})"></button>
            <p-menu #bulkMoveMenu [popup]="true" [model]="folderMenuItems()" />
          </div>
        }

        <p-table
          [value]="store.items()"
          [lazy]="true"
          [loading]="store.loading()"
          [paginator]="true"
          [rows]="store.filter().per_page"
          [totalRecords]="store.total()"
          [first]="(store.filter().page - 1) * store.filter().per_page"
          [rowsPerPageOptions]="[10, 20, 50, 100]"
          dataKey="id"
          (onLazyLoad)="onLazy($event)"
          responsiveLayout="scroll">

          <ng-template pTemplate="header">
            <tr>
              <th style="width:2.5rem">
                <p-checkbox
                  [binary]="true"
                  [ngModel]="allSelected()"
                  (onChange)="toggleAll($event.checked)" />
              </th>
              <th>{{ 'links.short_code' | translate }}</th>
              <th>{{ 'links.destination' | translate }}</th>
              <th class="text-right">{{ 'common.clicks' | translate }}</th>
              <!-- TODO(i18n): add key for "Status" column header -->
              <th>Status</th>
              <th>{{ 'links.created' | translate }}</th>
              <th class="text-right">{{ 'common.actions' | translate }}</th>
            </tr>
          </ng-template>

          <ng-template pTemplate="body" let-link>
            <tr>
              <td>
                <p-checkbox
                  [binary]="true"
                  [ngModel]="!!selected()[link.id]"
                  (onChange)="toggleOne(link.id, $event.checked)" />
              </td>
              <td>
                <div class="flex items-center gap-2">
                  <span
                    class="inline-block w-2 h-2 rounded-full shrink-0"
                    [class]="safetyDotClass(link.safety_status)"
                    [title]="safetyTitle(link.safety_status)"></span>
                  @if (link.favicon_url) {
                    <img [src]="link.favicon_url" alt="" width="16" height="16"
                         class="w-4 h-4 shrink-0" loading="lazy" />
                  }
                  <a [routerLink]="['/dashboard/links', link.id]"
                     class="font-mono text-brand-600 hover:underline">{{ link.short_code }}</a>
                </div>
              </td>
              <td class="max-w-md truncate">
                <div class="relative group">
                  <a [href]="link.long_url" target="_blank" rel="noopener"
                     class="text-slate-700 dark:text-slate-200 hover:underline" [title]="link.long_url">
                    {{ link.long_url }}
                  </a>
                  @if (link.og_image_url) {
                    <img [src]="link.og_image_url" alt=""
                         class="absolute left-0 top-full mt-1 w-10 h-10 object-cover rounded shadow hidden group-hover:block z-10"
                         loading="lazy" />
                  }
                </div>
              </td>
              <td class="text-right font-medium">{{ link.click_count }}</td>
              <td>
                @if (link.is_active) {
                  <p-tag severity="success" [value]="'links.active' | translate" />
                } @else {
                  <p-tag severity="danger" [value]="'links.disabled' | translate" />
                }
              </td>
              <td class="text-sm text-slate-500">{{ link.created_at | shortDate }}</td>
              <td class="text-right">
                <app-copy-button [value]="shortUrlFor(link)" />
                <button pButton class="p-button-sm p-button-text"
                        icon="pi pi-ellipsis-v"
                        (click)="openRowMenu($event, link)"
                        aria-label="More actions"></button>
                <button pButton class="p-button-sm p-button-text p-button-danger"
                        icon="pi pi-trash" (click)="askDelete(link)" aria-label="Delete"></button>
              </td>
            </tr>
          </ng-template>

          <ng-template pTemplate="emptymessage">
            <tr>
              <td colspan="7" class="!p-0">
                @if (!store.loading()) {
                  @if (store.filter().folder_id) {
                    <app-empty-state
                      icon="pi pi-folder-open"
                      [title]="'links.no_links' | translate"
                      [description]="'links.no_links_desc' | translate">
                      <a routerLink="/dashboard/links/new" class="btn-primary mt-4">{{ 'links.new_link' | translate }}</a>
                    </app-empty-state>
                  } @else {
                    <app-empty-state
                      icon="pi pi-link"
                      [title]="'links.no_links' | translate"
                      [description]="'links.no_links_desc' | translate">
                      <a routerLink="/dashboard/links/new" class="btn-primary mt-4">{{ 'links.new_link' | translate }}</a>
                    </app-empty-state>
                  }
                }
              </td>
            </tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <p-menu #rowMenu [popup]="true" [model]="rowMenuItems()" />

    <p-dialog
      [visible]="showImport()"
      (visibleChange)="showImport.set($event)"
      [modal]="true"
      [style]="{ width: '640px' }"
      header="Bulk import links"
      [draggable]="false">
      @if (showImport()) {
        <app-bulk-import (done)="onImportDone()" (closed)="showImport.set(false)" />
      }
    </p-dialog>
  `,
})
export class LinksListComponent implements OnInit {
  protected readonly store = inject(LinksStore);
  private readonly foldersApi = inject(FoldersApi);
  private readonly bulkApi = inject(BulkJobsApi);
  private readonly confirm = inject(ConfirmationService);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly search = signal('');
  readonly selected = signal<Record<string, boolean>>({});
  readonly folders = signal<FolderDto[]>([]);
  readonly showImport = signal(false);
  readonly exporting = signal(false);
  readonly activeRow = signal<UrlDto | null>(null);

  readonly selectedIds = computed(() =>
    Object.entries(this.selected())
      .filter(([, v]) => v)
      .map(([k]) => k),
  );

  readonly allSelected = computed(() => {
    const items = this.store.items();
    if (items.length === 0) return false;
    const sel = this.selected();
    return items.every((i) => sel[i.id]);
  });

  readonly folderMenuItems = computed<MenuItem[]>(() => [
    {
      label: '(none)',
      command: () => this.bulkMove(null),
    },
    ...this.folders().map((f) => ({
      label: f.name,
      command: () => this.bulkMove(f.id),
    })),
  ]);

  readonly rowMenuItems = computed<MenuItem[]>(() => {
    const row = this.activeRow();
    if (!row) return [];
    return [
      {
        label: 'Move to folder',
        icon: 'pi pi-folder',
        items: [
          {
            label: '(none)',
            command: () => this.moveRow(row, null),
          },
          ...this.folders().map((f) => ({
            label: f.name,
            command: () => this.moveRow(row, f.id),
          })),
        ],
      },
      {
        label: row.is_active ? 'Disable' : 'Enable',
        icon: row.is_active ? 'pi pi-ban' : 'pi pi-check',
        command: () => this.toggleActive(row),
      },
    ];
  });

  constructor() {
    toObservable(this.search)
      .pipe(
        skip(1),
        debounceTime(300),
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((q) => this.store.setQuery(q));
  }

  ngOnInit(): void {
    void this.store.load();
    this.foldersApi
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (l) => this.folders.set(l),
        error: () => this.folders.set([]),
      });
  }

  onLazy(event: TableLazyLoadEvent): void {
    const rows = event.rows ?? this.store.filter().per_page;
    const page = Math.floor((event.first ?? 0) / rows) + 1;
    if (rows !== this.store.filter().per_page) this.store.setPerPage(rows);
    if (page !== this.store.filter().page) this.store.setPage(page);
    if (event.sortField) {
      const dir = (event.sortOrder ?? 1) > 0 ? '' : '-';
      const field = Array.isArray(event.sortField) ? event.sortField[0] : event.sortField;
      this.store.setSort(`${dir}${field}`);
    }
  }

  onFolderChange(id: string | null): void {
    this.store.setFolder(id);
    this.selected.set({});
  }

  shortUrlFor(link: UrlDto): string {
    const base = environment.publicShortHost || globalThis.location?.origin || '';
    return `${base.replace(/\/$/, '')}/${link.short_code}`;
  }

  safetyDotClass(status: SafetyStatus): string {
    switch (status) {
      case 'ok': return 'bg-green-500';
      case 'warn': return 'bg-amber-500';
      case 'block': return 'bg-red-500';
      default: return 'bg-slate-300';
    }
  }

  safetyTitle(status: SafetyStatus): string {
    switch (status) {
      case 'ok': return 'Safety: OK';
      case 'warn': return 'Safety: Warning';
      case 'block': return 'Safety: Blocked';
      default: return 'Safety: Unchecked';
    }
  }

  toggleOne(id: string, checked: boolean): void {
    this.selected.update((s) => ({ ...s, [id]: checked }));
  }

  toggleAll(checked: boolean): void {
    const items = this.store.items();
    if (checked) {
      const next: Record<string, boolean> = {};
      items.forEach((i) => (next[i.id] = true));
      this.selected.set(next);
    } else {
      this.selected.set({});
    }
  }

  openRowMenu(event: MouseEvent, row: UrlDto): void {
    this.activeRow.set(row);
    // PrimeNG menu uses a viewchild; we use the shared #rowMenu
    const menu = document.querySelector('p-menu') as unknown as {
      toggle?: (e: unknown) => void;
    } | null;
    menu?.toggle?.(event);
  }

  async moveRow(link: UrlDto, folderId: string | null): Promise<void> {
    try {
      await this.store.update(link.id, { folder_id: folderId });
      this.toast.add({ severity: 'success', summary: 'Moved' });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Move failed', detail: (e as Error).message });
    }
  }

  async toggleActive(link: UrlDto): Promise<void> {
    try {
      await this.store.update(link.id, { is_active: !link.is_active });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Update failed', detail: (e as Error).message });
    }
  }

  async bulkMove(folderId: string | null): Promise<void> {
    const ids = this.selectedIds();
    if (ids.length === 0) return;
    try {
      await firstValueFrom(
        this.bulkApi.bulkPatch({ ids, patch: { folder_id: folderId } }),
      );
      this.toast.add({
        severity: 'success',
        summary: 'Moved',
        detail: `${ids.length} link(s)`,
      });
      this.selected.set({});
      void this.store.load();
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Bulk move failed', detail: (e as Error).message });
    }
  }

  async bulkDisable(): Promise<void> {
    const ids = this.selectedIds();
    if (ids.length === 0) return;
    try {
      await firstValueFrom(this.bulkApi.bulkPatch({ ids, patch: { is_active: false } }));
      this.toast.add({ severity: 'success', summary: 'Disabled', detail: `${ids.length} link(s)` });
      this.selected.set({});
      void this.store.load();
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Bulk disable failed', detail: (e as Error).message });
    }
  }

  bulkDelete(): void {
    const ids = this.selectedIds();
    if (ids.length === 0) return;
    this.confirm.confirm({
      header: 'Delete links?',
      message: `Permanently delete ${ids.length} link(s)? This cannot be undone.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      accept: async () => {
        try {
          await firstValueFrom(this.bulkApi.bulkPatch({ ids, patch: { delete: true } }));
          this.toast.add({ severity: 'success', summary: 'Deleted', detail: `${ids.length} link(s)` });
          this.selected.set({});
          void this.store.load();
        } catch (e) {
          this.toast.add({
            severity: 'error',
            summary: 'Bulk delete failed',
            detail: (e as Error).message,
          });
        }
      },
    });
  }

  async exportAll(): Promise<void> {
    this.exporting.set(true);
    try {
      const f = this.store.filter();
      let job = await firstValueFrom(
        this.bulkApi.exportCsv({ folder_id: f.folder_id, q: f.q }),
      );
      // Poll until done (max ~60s).
      for (let i = 0; i < 30 && job.status !== 'done' && job.status !== 'failed'; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        job = await firstValueFrom(this.bulkApi.get(job.id));
      }
      if (job.status === 'done' && job.result_url) {
        globalThis.open?.(job.result_url, '_blank');
        this.toast.add({ severity: 'success', summary: 'Export ready' });
      } else {
        this.toast.add({
          severity: 'warn',
          summary: 'Export still running',
          detail: `Check Bulk Jobs page (job ${job.id}).`,
        });
      }
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Export failed', detail: (e as Error).message });
    } finally {
      this.exporting.set(false);
    }
  }

  onImportDone(): void {
    this.showImport.set(false);
    void this.store.load();
  }

  askDelete(link: UrlDto): void {
    this.confirm.confirm({
      header: 'Delete link?',
      message: `Delete "${link.short_code}"? This cannot be undone.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      accept: async () => {
        try {
          await this.store.remove(link.id);
          this.toast.add({ severity: 'success', summary: 'Deleted', detail: link.short_code });
        } catch (e) {
          this.toast.add({
            severity: 'error',
            summary: 'Delete failed',
            detail: (e as Error).message,
          });
        }
      },
    });
  }
}
