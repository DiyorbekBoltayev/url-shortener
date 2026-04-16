import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  AsyncValidatorFn,
  FormControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Observable, catchError, map, of, switchMap, timer } from 'rxjs';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { CheckboxModule } from 'primeng/checkbox';
import { DatePickerModule } from 'primeng/datepicker';
import { AccordionModule } from 'primeng/accordion';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';
import { LinksStore } from './links.store';
import { UrlsApi } from '../../core/api/urls.api';
import { UtmBuilderComponent, UtmValue } from './utm-builder.component';

function urlValidator(ctrl: AbstractControl): ValidationErrors | null {
  const v = ctrl.value as string;
  if (!v) return null;
  try {
    const u = new URL(v);
    return u.protocol === 'http:' || u.protocol === 'https:' ? null : { url: true };
  } catch {
    return { url: true };
  }
}

function aliasUniqueValidator(api: UrlsApi): AsyncValidatorFn {
  return (ctrl: AbstractControl): Observable<ValidationErrors | null> => {
    const v = (ctrl.value as string | null)?.trim();
    if (!v) return of(null);
    return timer(300).pipe(
      switchMap(() => api.checkAlias(v)),
      map((r) => (r.available ? null : { taken: true })),
      catchError(() => of({ checkFailed: true })),
    );
  };
}

@Component({
  selector: 'app-link-create',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    ButtonModule,
    InputTextModule,
    CheckboxModule,
    DatePickerModule,
    AccordionModule,
    ToggleSwitchModule,
    TranslateModule,
    UtmBuilderComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center gap-2 mb-6">
      <a routerLink="/dashboard/links" class="btn-ghost">
        <i class="pi pi-arrow-left"></i>
      </a>
      <h1 class="page-title">{{ 'links.new_link_title' | translate }}</h1>
    </div>

    <form [formGroup]="form" (ngSubmit)="submit()" class="card max-w-2xl flex flex-col gap-4">
      <div>
        <label class="form-label" for="longUrl">{{ 'links.destination_url' | translate }} <span class="text-red-500">*</span></label>
        <input pInputText id="longUrl" formControlName="long_url" class="w-full"
               autofocus autocomplete="url"
               placeholder="https://example.com/very/long/path" />
        @if (form.controls.long_url.touched && form.controls.long_url.errors; as e) {
          @if (e['required']) { <small class="text-red-500">{{ 'links.url_required' | translate }}</small> }
          @else if (e['url']) { <small class="text-red-500">{{ 'links.url_invalid' | translate }}</small> }
        }
      </div>

      <div>
        <label class="form-label" for="alias">{{ 'links.custom_alias' | translate }}</label>
        <div class="flex items-center gap-2">
          <span class="text-slate-500 text-sm">/</span>
          <input pInputText id="alias" formControlName="custom_alias" class="flex-1" placeholder="my-link" />
        </div>
        <small class="text-slate-500">{{ 'links.alias_hint' | translate }}</small>
        @if (form.controls.custom_alias.pending) {
          <div><small class="text-slate-500"><i class="pi pi-spin pi-spinner text-xs"></i> {{ 'links.alias_checking' | translate }}</small></div>
        }
        @if (form.controls.custom_alias.errors; as e) {
          @if (e['pattern']) { <div><small class="text-red-500">{{ 'links.alias_invalid' | translate }}</small></div> }
          @else if (e['taken']) { <div><small class="text-red-500">{{ 'links.alias_taken' | translate }}</small></div> }
          @else if (e['checkFailed']) { <div><small class="text-amber-600">{{ 'links.alias_check_failed' | translate }}</small></div> }
        }
      </div>

      <div>
        <label class="form-label" for="expires">{{ 'links.expires_at' | translate }}</label>
        <p-datepicker id="expires" formControlName="expires_at" [showTime]="true"
                      styleClass="w-full" [placeholder]="'links.pick_date' | translate" />
      </div>

      <div>
        <label class="form-label" for="desc">{{ 'links.description' | translate }}</label>
        <input pInputText id="desc" formControlName="description" class="w-full"
               placeholder="What is this link for?" />
      </div>

      <div class="flex items-center gap-3">
        <p-toggleSwitch formControlName="preview_enabled" inputId="prev" />
        <label for="prev" class="text-sm">
          Show preview page (click-to-confirm)
        </label>
      </div>

      <p-accordion>
        <p-accordion-panel value="utm">
          <p-accordion-header>
            <i class="pi pi-tag mr-2"></i> Campaign / UTM
          </p-accordion-header>
          <p-accordion-content>
            <app-utm-builder formControlName="utm" />
          </p-accordion-content>
        </p-accordion-panel>
      </p-accordion>

      @if (error()) {
        <div class="text-sm text-red-600">{{ error() }}</div>
      }

      <div class="flex items-center gap-2">
        <button pButton type="submit" class="btn-primary"
                [disabled]="form.invalid || busy()"
                [label]="busy() ? ('links.creating' | translate) : ('links.create_link' | translate)"></button>
        <a routerLink="/dashboard/links" class="btn-ghost">{{ 'common.cancel' | translate }}</a>
      </div>
    </form>
  `,
})
export class LinkCreateComponent {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly api = inject(UrlsApi);
  private readonly store = inject(LinksStore);
  private readonly router = inject(Router);
  private readonly toast = inject(MessageService);

  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.group({
    long_url: this.fb.control('', { validators: [Validators.required, urlValidator] }),
    custom_alias: this.fb.control('', {
      validators: [Validators.pattern(/^[a-zA-Z0-9_-]{3,32}$/)],
      asyncValidators: [aliasUniqueValidator(this.api)],
      updateOn: 'change',
    }),
    expires_at: new FormControl<Date | null>(null),
    description: this.fb.control(''),
    preview_enabled: this.fb.control(false),
    utm: new FormControl<UtmValue | null>(null),
  });

  async submit(): Promise<void> {
    if (this.form.invalid) return;
    this.error.set(null);
    this.busy.set(true);
    const v = this.form.getRawValue();
    const utm = v.utm;
    try {
      const created = await this.store.create({
        long_url: v.long_url,
        custom_slug: v.custom_alias || undefined,
        expires_at: v.expires_at ? new Date(v.expires_at).toISOString() : undefined,
        title: v.description || undefined,
        preview_enabled: v.preview_enabled,
        utm_source: utm?.source || undefined,
        utm_medium: utm?.medium || undefined,
        utm_campaign: utm?.campaign || undefined,
        utm_term: utm?.term || undefined,
        utm_content: utm?.content || undefined,
      });
      this.toast.add({ severity: 'success', summary: 'Link created', detail: created.short_code });
      this.router.navigate(['/dashboard/links', created.id]);
    } catch (e) {
      this.error.set((e as Error).message || 'Failed to create link.');
    } finally {
      this.busy.set(false);
    }
  }
}
