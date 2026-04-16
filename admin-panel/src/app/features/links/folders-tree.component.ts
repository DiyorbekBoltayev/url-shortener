import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { TreeModule, TreeNodeSelectEvent } from 'primeng/tree';
import { TreeNode } from 'primeng/api';
import { ConfirmationService, MessageService } from 'primeng/api';
import { FoldersApi } from '../../core/api/folders.api';
import { FolderDto } from '../../core/models/folder.model';

interface FolderTreeData extends TreeNode {
  data: FolderDto;
  children: FolderTreeData[];
}

@Component({
  selector: 'app-folders-tree',
  standalone: true,
  imports: [FormsModule, ButtonModule, InputTextModule, TreeModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <h3 class="text-xs uppercase tracking-wide text-slate-500">Folders</h3>
        <button
          pButton
          type="button"
          class="p-button-text p-button-sm"
          icon="pi pi-plus"
          aria-label="New folder"
          (click)="startCreate()"></button>
      </div>

      <button
        type="button"
        class="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700"
        [class]="selectedId() === null ? 'bg-brand-50 dark:bg-brand-900/30' : ''"
        (click)="selectFolder(null)">
        <i class="pi pi-inbox text-xs text-slate-500"></i>
        <span>All links</span>
      </button>

      @if (creating()) {
        <div class="flex items-center gap-1 px-2">
          <input
            pInputText
            class="flex-1 !text-sm !py-1"
            placeholder="New folder name"
            [(ngModel)]="newName"
            (keydown.enter)="commitCreate()"
            (keydown.escape)="cancelCreate()" />
          <button
            pButton
            class="p-button-text p-button-sm"
            icon="pi pi-check"
            (click)="commitCreate()"
            aria-label="Confirm"></button>
          <button
            pButton
            class="p-button-text p-button-sm p-button-danger"
            icon="pi pi-times"
            (click)="cancelCreate()"
            aria-label="Cancel"></button>
        </div>
      }

      @if (loading()) {
        <div class="text-sm text-slate-500">Loading…</div>
      } @else if (nodes().length === 0) {
        <div class="text-xs text-slate-400 italic px-2">No folders yet.</div>
      } @else {
        <p-tree
          [value]="nodes()"
          selectionMode="single"
          [selection]="selectedNode()"
          (onNodeSelect)="onNodeSelect($event)"
          styleClass="!p-0 !bg-transparent !border-none">
          <ng-template let-node pTemplate="default">
            <span class="flex items-center gap-2 w-full">
              @if (node.data.color) {
                <span
                  class="inline-block w-2.5 h-2.5 rounded-full"
                  [style.background-color]="node.data.color"></span>
              } @else {
                <i class="pi pi-folder text-xs text-slate-400"></i>
              }
              @if (editingId() === node.data.id) {
                <input
                  pInputText
                  class="flex-1 !text-sm !py-0.5"
                  [(ngModel)]="editName"
                  (click)="$event.stopPropagation()"
                  (keydown.enter)="commitRename(node.data); $event.stopPropagation()"
                  (keydown.escape)="cancelRename(); $event.stopPropagation()" />
              } @else {
                <span class="flex-1 text-sm truncate">{{ node.data.name }}</span>
                <span class="text-xs text-slate-400">{{ node.data.links_count }}</span>
                <button
                  type="button"
                  class="p-button-text p-button-sm !p-0 opacity-0 hover:opacity-100"
                  title="Rename"
                  (click)="startRename(node.data); $event.stopPropagation()">
                  <i class="pi pi-pencil text-xs"></i>
                </button>
                <button
                  type="button"
                  class="p-button-text p-button-sm p-button-danger !p-0 opacity-0 hover:opacity-100"
                  title="Delete"
                  (click)="askDelete(node.data); $event.stopPropagation()">
                  <i class="pi pi-trash text-xs"></i>
                </button>
              }
            </span>
          </ng-template>
        </p-tree>
      }
    </div>
    <!-- TODO: drag-drop reorder/reparent (v1 disabled) -->
  `,
})
export class FoldersTreeComponent implements OnInit {
  readonly folderChange = output<string | null>();

  private readonly api = inject(FoldersApi);
  private readonly confirm = inject(ConfirmationService);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly folders = signal<FolderDto[]>([]);
  readonly loading = signal(false);
  readonly selectedId = signal<string | null>(null);
  readonly creating = signal(false);
  readonly editingId = signal<string | null>(null);
  newName = '';
  editName = '';

  readonly nodes = computed<FolderTreeData[]>(() => this.buildTree(this.folders()));
  readonly selectedNode = computed(() => {
    const id = this.selectedId();
    if (!id) return null;
    return findNode(this.nodes(), id);
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (list) => {
          this.folders.set(list);
          this.loading.set(false);
        },
        error: () => {
          this.folders.set([]);
          this.loading.set(false);
        },
      });
  }

  selectFolder(id: string | null): void {
    this.selectedId.set(id);
    this.folderChange.emit(id);
  }

  onNodeSelect(e: TreeNodeSelectEvent): void {
    const n = e.node as FolderTreeData;
    this.selectFolder(n.data.id);
  }

  startCreate(): void {
    this.creating.set(true);
    this.newName = '';
  }

  cancelCreate(): void {
    this.creating.set(false);
    this.newName = '';
  }

  commitCreate(): void {
    const name = this.newName.trim();
    if (!name) {
      this.cancelCreate();
      return;
    }
    this.api
      .create({ name, parent_id: this.selectedId() ?? null })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (f) => {
          this.folders.update((l) => [...l, f]);
          this.cancelCreate();
          this.toast.add({ severity: 'success', summary: 'Folder created', detail: f.name });
        },
        error: (e: Error) => {
          this.toast.add({ severity: 'error', summary: 'Create failed', detail: e.message });
        },
      });
  }

  startRename(f: FolderDto): void {
    this.editingId.set(f.id);
    this.editName = f.name;
  }

  cancelRename(): void {
    this.editingId.set(null);
    this.editName = '';
  }

  commitRename(f: FolderDto): void {
    const name = this.editName.trim();
    if (!name || name === f.name) {
      this.cancelRename();
      return;
    }
    this.api
      .update(f.id, { name })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.folders.update((l) => l.map((x) => (x.id === updated.id ? updated : x)));
          this.cancelRename();
        },
        error: (e: Error) => {
          this.toast.add({ severity: 'error', summary: 'Rename failed', detail: e.message });
        },
      });
  }

  askDelete(f: FolderDto): void {
    this.confirm.confirm({
      header: 'Delete folder?',
      message: `Delete "${f.name}"? Links inside will be unassigned.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      accept: () => {
        this.api
          .delete(f.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.folders.update((l) => l.filter((x) => x.id !== f.id));
              if (this.selectedId() === f.id) this.selectFolder(null);
              this.toast.add({ severity: 'success', summary: 'Deleted', detail: f.name });
            },
            error: (e: Error) => {
              this.toast.add({ severity: 'error', summary: 'Delete failed', detail: e.message });
            },
          });
      },
    });
  }

  private buildTree(flat: FolderDto[]): FolderTreeData[] {
    const byId = new Map<string, FolderTreeData>();
    flat.forEach((f) => {
      byId.set(f.id, {
        key: f.id,
        label: f.name,
        data: f,
        children: [],
      });
    });
    const roots: FolderTreeData[] = [];
    flat.forEach((f) => {
      const node = byId.get(f.id)!;
      if (f.parent_id && byId.has(f.parent_id)) {
        byId.get(f.parent_id)!.children.push(node);
      } else {
        roots.push(node);
      }
    });
    return roots;
  }
}

function findNode(nodes: FolderTreeData[], id: string): FolderTreeData | null {
  for (const n of nodes) {
    if (n.data.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}
