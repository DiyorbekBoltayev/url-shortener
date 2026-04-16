import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FormsModule,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { DialogModule } from 'primeng/dialog';
import { TableModule } from 'primeng/table';
import { ConfirmationService, MessageService } from 'primeng/api';
import { UtmTemplatesApi } from '../../core/api/utm-templates.api';
import { UtmTemplateDto } from '../../core/models/utm-template.model';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';

@Component({
  selector: 'app-settings-utm-templates',
  standalone: true,
  imports: [
    FormsModule,
    ReactiveFormsModule,
    ButtonModule,
    InputTextModule,
    DialogModule,
    TableModule,
    EmptyStateComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <h1 class="page-title">UTM templates</h1>
      <button pButton class="btn-primary" (click)="openCreate()">
        <i class="pi pi-plus"></i><span>New template</span>
      </button>
    </div>

    <div class="card">
      @if (loading()) {
        <div class="py-8 text-center text-slate-500">
          <i class="pi pi-spin pi-spinner mr-1"></i> Loading…
        </div>
      } @else if (templates().length === 0) {
        <app-empty-state icon="pi pi-tag" title="No templates"
                         description="Save UTM presets to reuse across links.">
          <button pButton class="btn-primary mt-4" label="New template" (click)="openCreate()"></button>
        </app-empty-state>
      } @else {
        <p-table [value]="templates()" responsiveLayout="scroll">
          <ng-template pTemplate="header">
            <tr>
              <th>Name</th>
              <th>Source</th>
              <th>Medium</th>
              <th>Campaign</th>
              <th class="text-right">Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-t>
            <tr>
              <td class="font-medium">{{ t.name }}</td>
              <td>{{ t.source ?? '—' }}</td>
              <td>{{ t.medium ?? '—' }}</td>
              <td>{{ t.campaign ?? '—' }}</td>
              <td class="text-right">
                <button pButton class="p-button-sm p-button-text"
                        icon="pi pi-pencil" (click)="openEdit(t)" aria-label="Edit"></button>
                <button pButton class="p-button-sm p-button-text p-button-danger"
                        icon="pi pi-trash" (click)="askDelete(t)" aria-label="Delete"></button>
              </td>
            </tr>
          </ng-template>
        </p-table>
      }
    </div>

    <p-dialog
      [visible]="showDialog()"
      (visibleChange)="showDialog.set($event)"
      [modal]="true"
      [style]="{ width: '480px' }"
      [header]="editing() ? 'Edit template' : 'New template'"
      [draggable]="false">
      <form [formGroup]="form" (ngSubmit)="save()" class="flex flex-col gap-3">
        <div>
          <label class="form-label">Name</label>
          <input pInputText formControlName="name" class="w-full" placeholder="e.g. Newsletter default" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="form-label">Source</label>
            <input pInputText formControlName="source" class="w-full" />
          </div>
          <div>
            <label class="form-label">Medium</label>
            <input pInputText formControlName="medium" class="w-full" />
          </div>
        </div>
        <div>
          <label class="form-label">Campaign</label>
          <input pInputText formControlName="campaign" class="w-full" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="form-label">Term</label>
            <input pInputText formControlName="term" class="w-full" />
          </div>
          <div>
            <label class="form-label">Content</label>
            <input pInputText formControlName="content" class="w-full" />
          </div>
        </div>
        <div class="flex items-center justify-end gap-2 mt-2">
          <button pButton type="button" class="btn-ghost" label="Cancel"
                  (click)="showDialog.set(false)"></button>
          <button pButton type="submit" class="btn-primary"
                  [disabled]="form.invalid || saving()"
                  [label]="saving() ? 'Saving…' : editing() ? 'Update' : 'Create'"></button>
        </div>
      </form>
    </p-dialog>
  `,
})
export class UtmTemplatesSettingsComponent implements OnInit {
  private readonly api = inject(UtmTemplatesApi);
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly toast = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);
  private readonly destroyRef = inject(DestroyRef);

  readonly templates = signal<UtmTemplateDto[]>([]);
  readonly loading = signal(false);
  readonly showDialog = signal(false);
  readonly saving = signal(false);
  readonly editing = signal<UtmTemplateDto | null>(null);

  readonly form = this.fb.group({
    name: this.fb.control('', { validators: [Validators.required] }),
    source: this.fb.control(''),
    medium: this.fb.control(''),
    campaign: this.fb.control(''),
    term: this.fb.control(''),
    content: this.fb.control(''),
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
        next: (l) => {
          this.templates.set(l);
          this.loading.set(false);
        },
        error: () => {
          this.templates.set([]);
          this.loading.set(false);
        },
      });
  }

  openCreate(): void {
    this.editing.set(null);
    this.form.reset({
      name: '',
      source: '',
      medium: '',
      campaign: '',
      term: '',
      content: '',
    });
    this.showDialog.set(true);
  }

  openEdit(t: UtmTemplateDto): void {
    this.editing.set(t);
    this.form.reset({
      name: t.name,
      source: t.source ?? '',
      medium: t.medium ?? '',
      campaign: t.campaign ?? '',
      term: t.term ?? '',
      content: t.content ?? '',
    });
    this.showDialog.set(true);
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    const v = this.form.getRawValue();
    const payload = {
      name: v.name,
      source: v.source || null,
      medium: v.medium || null,
      campaign: v.campaign || null,
      term: v.term || null,
      content: v.content || null,
    };
    const editing = this.editing();
    const obs = editing ? this.api.update(editing.id, payload) : this.api.create(payload);
    obs.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (t) => {
        if (editing) {
          this.templates.update((l) => l.map((x) => (x.id === t.id ? t : x)));
        } else {
          this.templates.update((l) => [...l, t]);
        }
        this.saving.set(false);
        this.showDialog.set(false);
        this.toast.add({ severity: 'success', summary: editing ? 'Updated' : 'Created' });
      },
      error: (e: Error) => {
        this.saving.set(false);
        this.toast.add({ severity: 'error', summary: 'Save failed', detail: e.message });
      },
    });
  }

  askDelete(t: UtmTemplateDto): void {
    this.confirm.confirm({
      header: 'Delete template?',
      message: `Delete "${t.name}"?`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      accept: () => {
        this.api
          .delete(t.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.templates.update((l) => l.filter((x) => x.id !== t.id));
              this.toast.add({ severity: 'success', summary: 'Deleted' });
            },
            error: (e: Error) => {
              this.toast.add({ severity: 'error', summary: 'Delete failed', detail: e.message });
            },
          });
      },
    });
  }
}
