import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { ProgressBarModule } from 'primeng/progressbar';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { StepperModule } from 'primeng/stepper';
import { MessageService } from 'primeng/api';
import { firstValueFrom } from 'rxjs';
import * as Papa from 'papaparse';
import { BulkJobsApi } from '../../core/api/bulk-jobs.api';
import { BulkJobDto, ColumnMap } from '../../core/models/bulk-job.model';

const BACKEND_FIELDS: { key: string; label: string; required?: boolean }[] = [
  { key: 'long_url', label: 'Destination URL', required: true },
  { key: 'title', label: 'Title' },
  { key: 'custom_slug', label: 'Custom slug' },
  { key: 'tag', label: 'Tag' },
  { key: 'folder_id', label: 'Folder ID' },
  { key: 'expires_at', label: 'Expires at (ISO8601)' },
];

@Component({
  selector: 'app-bulk-import',
  standalone: true,
  imports: [
    FormsModule,
    ButtonModule,
    InputTextModule,
    ProgressBarModule,
    SelectModule,
    TableModule,
    StepperModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex flex-col gap-4">
      <!-- Step indicator -->
      <div class="flex items-center gap-1 text-xs text-slate-500">
        @for (s of stepLabels; track s.idx) {
          <span
            class="px-2 py-0.5 rounded-full"
            [class.bg-brand-600]="step() === s.idx"
            [class.text-white]="step() === s.idx"
            [class.bg-slate-200]="step() !== s.idx"
            [class.text-slate-700]="step() !== s.idx && step() >= s.idx"
            [class.text-slate-400]="step() < s.idx">
            {{ s.idx }}. {{ s.label }}
          </span>
        }
      </div>

      @if (step() === 1) {
        <div class="flex flex-col items-center gap-3 py-6 border-2 border-dashed rounded-lg">
          <i class="pi pi-upload text-3xl text-slate-400"></i>
          <p class="text-sm text-slate-600">Drag and drop a CSV file here, or choose:</p>
          <input
            type="file"
            accept=".csv,text/csv"
            (change)="onFile($any($event.target).files?.[0])"
            class="text-sm" />
          <p class="text-xs text-slate-500">Max 1 MB. First row is assumed to be headers.</p>
          @if (parseError()) {
            <p class="text-sm text-red-600">{{ parseError() }}</p>
          }
        </div>
      }

      @if (step() === 2) {
        <p class="text-sm text-slate-500">
          Map your CSV columns to the link fields.
        </p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          @for (field of backendFields; track field.key) {
            <div>
              <label class="form-label">
                {{ field.label }}
                @if (field.required) { <span class="text-red-500">*</span> }
              </label>
              <p-select
                [options]="headerOptions()"
                optionLabel="label"
                optionValue="value"
                [ngModel]="columnMap()[field.key] || null"
                (ngModelChange)="setMap(field.key, $event)"
                placeholder="— skip —"
                [showClear]="true"
                styleClass="w-full" />
            </div>
          }
        </div>
        <div>
          <h4 class="text-xs uppercase tracking-wide text-slate-500 mb-2">Preview (first 5 rows)</h4>
          <div class="overflow-auto max-h-48 border rounded">
            <table class="text-xs w-full">
              <thead class="bg-slate-100 dark:bg-slate-700">
                <tr>
                  @for (h of headers(); track h) { <th class="px-2 py-1 text-left">{{ h }}</th> }
                </tr>
              </thead>
              <tbody>
                @for (r of previewRows(); track $index) {
                  <tr class="border-t border-slate-200">
                    @for (h of headers(); track h) {
                      <td class="px-2 py-1 truncate max-w-[200px]">{{ r[h] }}</td>
                    }
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }

      @if (step() === 3) {
        <p class="text-sm text-slate-500">
          Validated {{ validCount() }} of {{ rows().length }} rows. Invalid rows
          will be skipped and reported.
        </p>
        <div class="overflow-auto max-h-64 border rounded">
          <table class="text-xs w-full">
            <thead class="bg-slate-100 dark:bg-slate-700">
              <tr>
                <th class="px-2 py-1 text-left">#</th>
                <th class="px-2 py-1 text-left">Destination</th>
                <th class="px-2 py-1 text-left">Valid</th>
              </tr>
            </thead>
            <tbody>
              @for (r of validationPreview(); track $index) {
                <tr class="border-t border-slate-200">
                  <td class="px-2 py-1">{{ $index + 1 }}</td>
                  <td class="px-2 py-1 truncate max-w-md">{{ r.url }}</td>
                  <td class="px-2 py-1">
                    @if (r.valid) {
                      <span class="text-green-600">OK</span>
                    } @else {
                      <span class="text-red-600">{{ r.reason }}</span>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (step() === 4) {
        @if (job(); as j) {
          <div class="flex flex-col gap-2">
            <div class="text-sm">
              Status: <strong>{{ j.status }}</strong>
              · {{ j.done }} / {{ j.total }} processed
              · {{ j.failed }} failed
            </div>
            <p-progressBar [value]="progressPct()" />
            @if (j.status === 'done') {
              <div class="text-green-600 text-sm">
                <i class="pi pi-check-circle"></i> Import complete.
                @if (j.result_url) {
                  <a [href]="j.result_url" target="_blank" class="ml-2 underline">
                    Download error report
                  </a>
                }
              </div>
            } @else if (j.status === 'failed') {
              <div class="text-red-600 text-sm">
                <i class="pi pi-times-circle"></i>
                Import failed. {{ j.error_message ?? '' }}
              </div>
            }
          </div>
        } @else {
          <div class="text-sm text-slate-500">Submitting…</div>
        }
      }

      <!-- Controls -->
      <div class="flex items-center justify-end gap-2 border-t pt-3">
        <button pButton type="button" class="btn-ghost" label="Cancel"
                (click)="closed.emit()"></button>
        @if (step() > 1 && step() < 4) {
          <button pButton type="button" class="btn-ghost" label="Back"
                  (click)="step.set(step() - 1)"></button>
        }
        @if (step() === 1) {
          <button pButton type="button" class="btn-primary" label="Next"
                  [disabled]="rows().length === 0" (click)="step.set(2)"></button>
        }
        @if (step() === 2) {
          <button pButton type="button" class="btn-primary" label="Next"
                  [disabled]="!hasRequiredMap()" (click)="goPreview()"></button>
        }
        @if (step() === 3) {
          <button pButton type="button" class="btn-primary" label="Import"
                  [disabled]="validCount() === 0 || submitting()"
                  (click)="submit()"></button>
        }
        @if (step() === 4 && isFinished()) {
          <button pButton type="button" class="btn-primary" label="Done"
                  (click)="done.emit()"></button>
        }
      </div>
    </div>
  `,
})
export class BulkImportComponent {
  readonly done = output<void>();
  readonly closed = output<void>();

  readonly backendFields = BACKEND_FIELDS;

  private readonly api = inject(BulkJobsApi);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly step = signal(1);
  readonly stepLabels = [
    { idx: 1, label: 'Upload' },
    { idx: 2, label: 'Map columns' },
    { idx: 3, label: 'Preview' },
    { idx: 4, label: 'Commit' },
  ];

  readonly file = signal<File | null>(null);
  readonly parseError = signal<string | null>(null);
  readonly headers = signal<string[]>([]);
  readonly rows = signal<Record<string, string>[]>([]);
  readonly columnMap = signal<ColumnMap>({});
  readonly job = signal<BulkJobDto | null>(null);
  readonly submitting = signal(false);
  private pollHandle: ReturnType<typeof setInterval> | null = null;

  readonly previewRows = computed(() => this.rows().slice(0, 5));

  readonly headerOptions = computed(() =>
    this.headers().map((h) => ({ label: h, value: h })),
  );

  readonly validationPreview = computed(() => {
    const map = this.columnMap();
    const urlCol = map['long_url'];
    if (!urlCol) return [];
    return this.rows().slice(0, 20).map((r) => {
      const url = r[urlCol] ?? '';
      let valid = false;
      let reason = '';
      try {
        const u = new URL(url);
        valid = u.protocol === 'http:' || u.protocol === 'https:';
        if (!valid) reason = 'Non-http(s) URL';
      } catch {
        reason = 'Invalid URL';
      }
      return { url, valid, reason };
    });
  });

  readonly validCount = computed(() => {
    const map = this.columnMap();
    const urlCol = map['long_url'];
    if (!urlCol) return 0;
    return this.rows().filter((r) => {
      try {
        const u = new URL(r[urlCol] ?? '');
        return u.protocol === 'http:' || u.protocol === 'https:';
      } catch {
        return false;
      }
    }).length;
  });

  readonly progressPct = computed(() => {
    const j = this.job();
    if (!j || j.total === 0) return 0;
    return Math.min(100, Math.round(((j.done + j.failed) / j.total) * 100));
  });

  isFinished(): boolean {
    const s = this.job()?.status;
    return s === 'done' || s === 'failed';
  }

  hasRequiredMap(): boolean {
    const map = this.columnMap();
    return BACKEND_FIELDS.every((f) => !f.required || !!map[f.key]);
  }

  onFile(file?: File): void {
    this.parseError.set(null);
    if (!file) return;
    if (file.size > 1_000_000) {
      this.parseError.set('File is larger than 1 MB.');
      return;
    }
    this.file.set(file);
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (result) => {
        if (result.errors.length > 0) {
          this.parseError.set(result.errors[0].message);
          return;
        }
        const headers = (result.meta.fields ?? []).map((h) => h.trim()).filter(Boolean);
        this.headers.set(headers);
        this.rows.set(result.data as Record<string, string>[]);
        // auto-map any exact matches
        const auto: ColumnMap = {};
        for (const f of BACKEND_FIELDS) {
          const hit = headers.find((h) => h.toLowerCase() === f.key.toLowerCase());
          if (hit) auto[f.key] = hit;
        }
        this.columnMap.set(auto);
      },
      error: (err) => this.parseError.set(err.message),
    });
  }

  setMap(key: string, header: string | null): void {
    this.columnMap.update((m) => {
      const next = { ...m };
      if (header) next[key] = header;
      else delete next[key];
      return next;
    });
  }

  goPreview(): void {
    if (!this.hasRequiredMap()) return;
    this.step.set(3);
  }

  async submit(): Promise<void> {
    const f = this.file();
    if (!f) return;
    this.submitting.set(true);
    try {
      const job = await firstValueFrom(this.api.importCsv(f, this.columnMap()));
      this.job.set(job);
      this.step.set(4);
      this.startPolling();
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Import failed', detail: (e as Error).message });
    } finally {
      this.submitting.set(false);
    }
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollHandle = setInterval(async () => {
      const j = this.job();
      if (!j) return;
      try {
        const updated = await firstValueFrom(this.api.get(j.id));
        this.job.set(updated);
        if (updated.status === 'done' || updated.status === 'failed') {
          this.stopPolling();
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
    // Stop polling on destroy.
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  private stopPolling(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }
}
