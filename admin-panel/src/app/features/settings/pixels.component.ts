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
import {
  FormsModule,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { DialogModule } from 'primeng/dialog';
import { TableModule } from 'primeng/table';
import { InputSwitchModule } from 'primeng/inputswitch';
import { TagModule } from 'primeng/tag';
import { ConfirmationService, MessageService } from 'primeng/api';
import { PixelsApi } from '../../core/api/pixels.api';
import {
  PIXEL_KIND_HELP,
  PIXEL_KIND_LABELS,
  PixelDto,
  PixelKind,
} from '../../core/models/pixel.model';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';

@Component({
  selector: 'app-settings-pixels',
  standalone: true,
  imports: [
    FormsModule,
    ReactiveFormsModule,
    ButtonModule,
    InputTextModule,
    SelectModule,
    DialogModule,
    TableModule,
    InputSwitchModule,
    TagModule,
    EmptyStateComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <h1 class="page-title">Tracking pixels</h1>
      <button pButton class="btn-primary" (click)="openCreate()">
        <i class="pi pi-plus"></i><span>New pixel</span>
      </button>
    </div>

    <div class="card">
      @if (loading()) {
        <div class="py-8 text-center text-slate-500">
          <i class="pi pi-spin pi-spinner mr-1"></i> Loading…
        </div>
      } @else if (pixels().length === 0) {
        <app-empty-state icon="pi pi-hashtag" title="No pixels configured"
                         description="Add a tracking pixel to fire on every click.">
          <button pButton class="btn-primary mt-4" label="New pixel" (click)="openCreate()"></button>
        </app-empty-state>
      } @else {
        <p-table [value]="pixels()" responsiveLayout="scroll">
          <ng-template pTemplate="header">
            <tr>
              <th>Name</th>
              <th>Kind</th>
              <th>Pixel ID</th>
              <th>Active</th>
              <th class="text-right">Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-p>
            <tr>
              <td class="font-medium">{{ p.name }}</td>
              <td><p-tag [value]="labelFor(p.kind)" severity="info" /></td>
              <td class="font-mono text-xs">{{ p.pixel_id }}</td>
              <td>
                <p-inputSwitch
                  [ngModel]="p.is_active"
                  (onChange)="toggleActive(p, $event.checked)" />
              </td>
              <td class="text-right">
                <button pButton class="p-button-sm p-button-text"
                        icon="pi pi-pencil" (click)="openEdit(p)" aria-label="Edit"></button>
                <button pButton class="p-button-sm p-button-text p-button-danger"
                        icon="pi pi-trash" (click)="askDelete(p)" aria-label="Delete"></button>
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
      [header]="editing() ? 'Edit pixel' : 'New pixel'"
      [draggable]="false">
      <form [formGroup]="form" (ngSubmit)="save()" class="flex flex-col gap-3">
        <div>
          <label class="form-label" for="p-kind">Platform</label>
          <p-select
            inputId="p-kind"
            [options]="kindOptions"
            optionLabel="label"
            optionValue="value"
            formControlName="kind"
            styleClass="w-full" />
        </div>
        <div>
          <label class="form-label" for="p-name">Name</label>
          <input pInputText id="p-name" formControlName="name" class="w-full"
                 placeholder="e.g. Main FB pixel" />
        </div>
        <div>
          <label class="form-label" for="p-id">Pixel ID</label>
          <input pInputText id="p-id" formControlName="pixel_id" class="w-full"
                 placeholder="123456789012345" />
          <small class="text-slate-500">{{ helpFor(form.controls.kind.value) }}</small>
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
export class PixelsSettingsComponent implements OnInit {
  private readonly api = inject(PixelsApi);
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly toast = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);
  private readonly destroyRef = inject(DestroyRef);

  readonly pixels = signal<PixelDto[]>([]);
  readonly loading = signal(false);
  readonly showDialog = signal(false);
  readonly editing = signal<PixelDto | null>(null);
  readonly saving = signal(false);

  readonly kindOptions: { label: string; value: PixelKind }[] = (
    Object.keys(PIXEL_KIND_LABELS) as PixelKind[]
  ).map((k) => ({ label: PIXEL_KIND_LABELS[k], value: k }));

  readonly form = this.fb.group({
    kind: this.fb.control<PixelKind>('fb', { validators: [Validators.required] }),
    name: this.fb.control('', { validators: [Validators.required] }),
    pixel_id: this.fb.control('', { validators: [Validators.required] }),
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
          this.pixels.set(l);
          this.loading.set(false);
        },
        error: () => {
          this.pixels.set([]);
          this.loading.set(false);
        },
      });
  }

  labelFor(k: PixelKind): string {
    return PIXEL_KIND_LABELS[k] ?? k;
  }

  helpFor(k: PixelKind): string {
    return PIXEL_KIND_HELP[k] ?? '';
  }

  openCreate(): void {
    this.editing.set(null);
    this.form.reset({ kind: 'fb', name: '', pixel_id: '' });
    this.showDialog.set(true);
  }

  openEdit(p: PixelDto): void {
    this.editing.set(p);
    this.form.reset({ kind: p.kind, name: p.name, pixel_id: p.pixel_id });
    this.showDialog.set(true);
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    const v = this.form.getRawValue();
    const editing = this.editing();
    const obs = editing
      ? this.api.update(editing.id, v)
      : this.api.create({ ...v, is_active: true });
    obs.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (p) => {
        if (editing) {
          this.pixels.update((l) => l.map((x) => (x.id === p.id ? p : x)));
        } else {
          this.pixels.update((l) => [...l, p]);
        }
        this.saving.set(false);
        this.showDialog.set(false);
        this.toast.add({
          severity: 'success',
          summary: editing ? 'Pixel updated' : 'Pixel created',
        });
      },
      error: (e: Error) => {
        this.saving.set(false);
        this.toast.add({ severity: 'error', summary: 'Save failed', detail: e.message });
      },
    });
  }

  toggleActive(p: PixelDto, active: boolean): void {
    this.api
      .update(p.id, { is_active: active })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.pixels.update((l) => l.map((x) => (x.id === updated.id ? updated : x)));
        },
        error: (e: Error) => {
          this.toast.add({ severity: 'error', summary: 'Update failed', detail: e.message });
        },
      });
  }

  askDelete(p: PixelDto): void {
    this.confirm.confirm({
      header: 'Delete pixel?',
      message: `Delete "${p.name}"? This will detach it from all links.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      accept: () => {
        this.api
          .delete(p.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.pixels.update((l) => l.filter((x) => x.id !== p.id));
              this.toast.add({ severity: 'success', summary: 'Deleted', detail: p.name });
            },
            error: (e: Error) => {
              this.toast.add({ severity: 'error', summary: 'Delete failed', detail: e.message });
            },
          });
      },
    });
  }
}
