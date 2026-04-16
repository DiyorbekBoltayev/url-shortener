import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { OverlayPanelModule, OverlayPanel } from 'primeng/overlaypanel';
import { TagModule } from 'primeng/tag';
import { MessageService } from 'primeng/api';
import { WorkspacesApi } from '../api/workspaces.api';
import { WorkspaceDto } from '../models/workspace.model';
import { AuthService } from '../auth/auth.service';

@Component({
  selector: 'app-workspace-switcher',
  standalone: true,
  imports: [ButtonModule, OverlayPanelModule, TagModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      pButton
      type="button"
      class="btn-ghost !px-2 flex items-center gap-2"
      (click)="panel.toggle($event)"
      aria-label="Switch workspace">
      <i class="pi pi-building text-sm"></i>
      @if (current(); as w) {
        <span class="hidden sm:inline text-sm font-medium text-slate-700 dark:text-slate-200">
          {{ w.name }}
        </span>
        <p-tag
          [value]="w.plan"
          severity="info"
          styleClass="!text-[10px] !py-0.5 !px-1.5 hidden sm:inline-flex" />
      } @else {
        <span class="hidden sm:inline text-sm text-slate-500">Workspace</span>
      }
      <i class="pi pi-angle-down text-xs"></i>
    </button>

    <p-overlayPanel #panel [showCloseIcon]="false" styleClass="!min-w-[260px]">
      <div class="py-1">
        <div class="px-3 py-1.5 text-xs uppercase tracking-wide text-slate-500">
          Your workspaces
        </div>
        @if (loading()) {
          <div class="px-3 py-2 text-sm text-slate-500">
            <i class="pi pi-spin pi-spinner text-xs mr-1"></i> Loading…
          </div>
        } @else if (workspaces().length === 0) {
          <div class="px-3 py-2 text-sm text-slate-500">No workspaces yet.</div>
        } @else {
          @for (w of workspaces(); track w.id) {
            <button
              type="button"
              class="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700"
              [class]="isCurrent(w) ? 'bg-brand-50 dark:bg-brand-900/30' : ''"
              (click)="select(w); panel.hide()">
              <div class="flex flex-col">
                <span class="font-medium text-slate-800 dark:text-slate-100">{{ w.name }}</span>
                <span class="text-xs text-slate-500">{{ w.role }} · {{ w.plan }}</span>
              </div>
              @if (isCurrent(w)) {
                <i class="pi pi-check text-brand-600"></i>
              } @else if (switchingId() === w.id) {
                <i class="pi pi-spin pi-spinner text-xs text-slate-500"></i>
              }
            </button>
          }
        }
        <div class="border-t border-slate-200 dark:border-slate-700 mt-1 pt-1">
          <a
            href="mailto:support@example.com?subject=New%20workspace"
            class="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
            (click)="panel.hide()">
            <i class="pi pi-plus text-xs"></i> Create workspace
          </a>
        </div>
      </div>
    </p-overlayPanel>
  `,
})
export class WorkspaceSwitcherComponent implements OnInit {
  private readonly api = inject(WorkspacesApi);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly workspaces = signal<WorkspaceDto[]>([]);
  readonly loading = signal(false);
  readonly currentId = signal<string | null>(null);
  readonly switchingId = signal<string | null>(null);

  readonly current = computed(() => {
    const id = this.currentId();
    return this.workspaces().find((w) => w.id === id) ?? this.workspaces()[0] ?? null;
  });

  ngOnInit(): void {
    this.fetch();
  }

  isCurrent(w: WorkspaceDto): boolean {
    return this.current()?.id === w.id;
  }

  fetch(): void {
    this.loading.set(true);
    this.api
      .myWorkspaces()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (list) => {
          this.workspaces.set(list);
          if (!this.currentId() && list.length > 0) {
            this.currentId.set(list[0].id);
          }
          this.loading.set(false);
        },
        error: () => {
          this.workspaces.set([]);
          this.loading.set(false);
        },
      });
  }

  select(w: WorkspaceDto): void {
    if (this.isCurrent(w)) return;
    this.switchingId.set(w.id);
    this.api
      .switch(w.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.auth.applySwitchedAccessToken(res.access_token);
          this.currentId.set(w.id);
          this.switchingId.set(null);
          this.toast.add({
            severity: 'success',
            summary: 'Workspace switched',
            detail: w.name,
          });
          // Reload current route to re-fetch workspace-scoped data.
          const url = this.router.url;
          this.router
            .navigateByUrl('/dashboard', { skipLocationChange: true })
            .then(() => this.router.navigateByUrl(url));
        },
        error: (e: Error) => {
          this.switchingId.set(null);
          this.toast.add({
            severity: 'error',
            summary: 'Switch failed',
            detail: e.message,
          });
        },
      });
  }
}
