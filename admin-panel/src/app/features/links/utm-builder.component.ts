import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  forwardRef,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  ControlValueAccessor,
  FormsModule,
  NG_VALUE_ACCESSOR,
  ReactiveFormsModule,
  NonNullableFormBuilder,
} from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { MessageService } from 'primeng/api';
import { UtmTemplatesApi } from '../../core/api/utm-templates.api';
import { UtmTemplateDto } from '../../core/models/utm-template.model';

export interface UtmValue {
  source: string;
  medium: string;
  campaign: string;
  term: string;
  content: string;
}

function empty(): UtmValue {
  return { source: '', medium: '', campaign: '', term: '', content: '' };
}

@Component({
  selector: 'app-utm-builder',
  standalone: true,
  imports: [FormsModule, ReactiveFormsModule, ButtonModule, InputTextModule, SelectModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => UtmBuilderComponent),
      multi: true,
    },
  ],
  template: `
    <div class="flex flex-col gap-3">
      <div class="flex items-center gap-2">
        <p-select
          [options]="templateOptions()"
          optionLabel="label"
          optionValue="value"
          placeholder="Load template…"
          [ngModel]="null"
          (ngModelChange)="loadTemplate($event)"
          styleClass="flex-1" />
        <button pButton type="button" class="btn-ghost" icon="pi pi-refresh"
                (click)="reload()" aria-label="Reload templates"></button>
      </div>

      <form [formGroup]="form" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label class="form-label" for="utm-src">Source</label>
          <input pInputText id="utm-src" formControlName="source" class="w-full"
                 placeholder="newsletter" />
        </div>
        <div>
          <label class="form-label" for="utm-med">Medium</label>
          <input pInputText id="utm-med" formControlName="medium" class="w-full"
                 placeholder="email" />
        </div>
        <div class="sm:col-span-2">
          <label class="form-label" for="utm-cmp">Campaign</label>
          <input pInputText id="utm-cmp" formControlName="campaign" class="w-full"
                 placeholder="spring_sale" />
        </div>
        <div>
          <label class="form-label" for="utm-trm">Term</label>
          <input pInputText id="utm-trm" formControlName="term" class="w-full"
                 placeholder="running+shoes" />
        </div>
        <div>
          <label class="form-label" for="utm-ctn">Content</label>
          <input pInputText id="utm-ctn" formControlName="content" class="w-full"
                 placeholder="hero-banner" />
        </div>
      </form>

      @if (preview()) {
        <div class="text-xs text-slate-500 break-all">
          <span class="uppercase tracking-wide">Preview:</span>
          <code class="ml-1 text-brand-600">{{ preview() }}</code>
        </div>
      }

      <div class="flex items-center gap-2">
        <input pInputText class="flex-1 !text-sm" placeholder="Template name"
               [(ngModel)]="templateName" />
        <button pButton type="button" class="p-button-sm"
                label="Save as template"
                [disabled]="!templateName.trim() || savingTemplate()"
                (click)="saveTemplate()"></button>
      </div>
      <!-- TODO: template list reorder -->
    </div>
  `,
})
export class UtmBuilderComponent implements ControlValueAccessor, OnInit {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly api = inject(UtmTemplatesApi);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly form = this.fb.group({
    source: this.fb.control(''),
    medium: this.fb.control(''),
    campaign: this.fb.control(''),
    term: this.fb.control(''),
    content: this.fb.control(''),
  });

  readonly templates = signal<UtmTemplateDto[]>([]);
  readonly savingTemplate = signal(false);
  templateName = '';

  readonly templateOptions = computed(() =>
    this.templates().map((t) => ({ label: t.name, value: t.id })),
  );

  readonly preview = computed(() => {
    const v = this.formValue();
    const parts: string[] = [];
    if (v.source) parts.push(`utm_source=${encodeURIComponent(v.source)}`);
    if (v.medium) parts.push(`utm_medium=${encodeURIComponent(v.medium)}`);
    if (v.campaign) parts.push(`utm_campaign=${encodeURIComponent(v.campaign)}`);
    if (v.term) parts.push(`utm_term=${encodeURIComponent(v.term)}`);
    if (v.content) parts.push(`utm_content=${encodeURIComponent(v.content)}`);
    return parts.length ? '?' + parts.join('&') : '';
  });

  private onChange: (v: UtmValue) => void = () => void 0;
  private onTouched: () => void = () => void 0;

  private formValue(): UtmValue {
    return this.form.getRawValue();
  }

  ngOnInit(): void {
    this.reload();
    this.form.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.onChange(this.formValue());
      });
  }

  reload(): void {
    this.api
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (l) => this.templates.set(l),
        error: () => this.templates.set([]),
      });
  }

  loadTemplate(id: string | null): void {
    if (!id) return;
    const t = this.templates().find((x) => x.id === id);
    if (!t) return;
    this.form.setValue({
      source: t.source ?? '',
      medium: t.medium ?? '',
      campaign: t.campaign ?? '',
      term: t.term ?? '',
      content: t.content ?? '',
    });
    this.toast.add({ severity: 'info', summary: 'Template loaded', detail: t.name });
  }

  saveTemplate(): void {
    const name = this.templateName.trim();
    if (!name) return;
    this.savingTemplate.set(true);
    const v = this.formValue();
    this.api
      .create({
        name,
        source: v.source || null,
        medium: v.medium || null,
        campaign: v.campaign || null,
        term: v.term || null,
        content: v.content || null,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (t) => {
          this.templates.update((l) => [...l, t]);
          this.templateName = '';
          this.savingTemplate.set(false);
          this.toast.add({ severity: 'success', summary: 'Template saved', detail: t.name });
        },
        error: (e: Error) => {
          this.savingTemplate.set(false);
          this.toast.add({ severity: 'error', summary: 'Save failed', detail: e.message });
        },
      });
  }

  // --- ControlValueAccessor ---
  writeValue(v: Partial<UtmValue> | null): void {
    this.form.setValue({ ...empty(), ...(v ?? {}) }, { emitEvent: false });
  }

  registerOnChange(fn: (v: UtmValue) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(disabled: boolean): void {
    disabled ? this.form.disable() : this.form.enable();
  }
}
