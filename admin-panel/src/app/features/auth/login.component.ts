import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { CardModule } from 'primeng/card';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ButtonModule, InputTextModule, PasswordModule, CardModule, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div class="w-full max-w-md">
        <div class="text-center mb-6">
          <div class="inline-flex items-center justify-center w-12 h-12 rounded-md bg-brand-600 text-white mb-2">
            <i class="pi pi-link text-lg"></i>
          </div>
          <h1 class="text-2xl font-semibold">{{ 'auth.login_title' | translate }}</h1>
          <p class="text-sm text-slate-500">{{ 'auth.login_subtitle' | translate }}</p>
        </div>

        <p-card>
          <form [formGroup]="form" (ngSubmit)="submit()" class="flex flex-col gap-4">
            <div>
              <label class="form-label" for="email">{{ 'auth.email' | translate }}</label>
              <input pInputText id="email" type="email" formControlName="email" class="w-full" autocomplete="email" autofocus />
              @if (form.controls.email.touched && form.controls.email.invalid) {
                <small class="text-red-500">{{ 'auth.email_invalid' | translate }}</small>
              }
            </div>

            <div>
              <label class="form-label" for="password">{{ 'auth.password' | translate }}</label>
              <p-password id="password" formControlName="password" styleClass="w-full"
                          [feedback]="false" [toggleMask]="true" inputStyleClass="w-full" autocomplete="current-password" />
              @if (form.controls.password.touched && form.controls.password.invalid) {
                <small class="text-red-500">{{ 'auth.password_required' | translate }}</small>
              }
            </div>

            @if (error()) {
              <div class="text-sm text-red-600">{{ error() }}</div>
            }

            <button pButton type="submit" class="w-full"
                    [disabled]="form.invalid || busy()"
                    [label]="busy() ? ('auth.signing_in' | translate) : ('auth.sign_in' | translate)"></button>
          </form>
        </p-card>

        <p class="mt-4 text-center text-sm text-slate-500">
          {{ 'auth.no_account' | translate }}
          <a routerLink="/register" class="text-brand-600 hover:underline">{{ 'auth.create_one' | translate }}</a>
        </p>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly translate = inject(TranslateService);

  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.group({
    email: this.fb.control('', { validators: [Validators.required, Validators.email] }),
    password: this.fb.control('', { validators: [Validators.required, Validators.minLength(6)] }),
  });

  submit(): void {
    if (this.busy() || this.form.invalid) return;
    this.error.set(null);
    this.busy.set(true);
    this.auth
      .login(this.form.getRawValue())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.router.navigateByUrl('/dashboard');
        },
        error: (e: { error?: { error?: { message?: string } }; message?: string }) => {
          this.error.set(
            e?.error?.error?.message ?? e?.message ?? this.translate.instant('auth.login_failed'),
          );
          this.busy.set(false);
        },
      });
  }
}
