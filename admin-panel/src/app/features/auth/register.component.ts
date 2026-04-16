import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { CardModule } from 'primeng/card';
import { TranslateModule } from '@ngx-translate/core';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ButtonModule, InputTextModule, PasswordModule, CardModule, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div class="w-full max-w-md">
        <div class="text-center mb-6">
          <h1 class="text-2xl font-semibold">{{ 'auth.register_title' | translate }}</h1>
          <p class="text-sm text-slate-500">{{ 'auth.register_subtitle' | translate }}</p>
        </div>

        <p-card>
          <form [formGroup]="form" (ngSubmit)="submit()" class="flex flex-col gap-4">
            <div>
              <label class="form-label" for="name">{{ 'auth.name' | translate }}</label>
              <input pInputText id="name" formControlName="full_name" class="w-full" autocomplete="name" autofocus />
            </div>

            <div>
              <label class="form-label" for="email">{{ 'auth.email' | translate }}</label>
              <input pInputText id="email" type="email" formControlName="email" class="w-full" autocomplete="email" />
              @if (form.controls.email.touched && form.controls.email.invalid) {
                <small class="text-red-500">{{ 'auth.email_invalid' | translate }}</small>
              }
            </div>

            <div>
              <label class="form-label" for="password">{{ 'auth.password' | translate }}</label>
              <p-password id="password" formControlName="password" styleClass="w-full"
                          [toggleMask]="true" inputStyleClass="w-full" autocomplete="new-password" />
              @if (form.controls.password.touched && form.controls.password.invalid) {
                <small class="text-red-500">{{ 'auth.password_min' | translate }}</small>
              }
            </div>

            @if (error()) {
              <div class="text-sm text-red-600">{{ error() }}</div>
            }

            <button pButton type="submit" class="w-full"
                    [disabled]="form.invalid || busy()"
                    [label]="busy() ? ('auth.creating' | translate) : ('auth.create_account' | translate)"></button>
          </form>
        </p-card>

        <p class="mt-4 text-center text-sm text-slate-500">
          {{ 'auth.have_account' | translate }}
          <a routerLink="/login" class="text-brand-600 hover:underline">{{ 'auth.sign_in_link' | translate }}</a>
        </p>
      </div>
    </div>
  `,
})
export class RegisterComponent {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.group({
    full_name: this.fb.control(''),
    email: this.fb.control('', { validators: [Validators.required, Validators.email] }),
    password: this.fb.control('', { validators: [Validators.required, Validators.minLength(8)] }),
  });

  submit(): void {
    if (this.busy() || this.form.invalid) return;
    this.error.set(null);
    this.busy.set(true);
    this.auth
      .register(this.form.getRawValue())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.router.navigateByUrl('/dashboard');
        },
        error: (e: { error?: { error?: { message?: string } }; message?: string }) => {
          this.error.set(e?.error?.error?.message ?? e?.message ?? 'Registration failed.');
          this.busy.set(false);
        },
      });
  }
}
