import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { TagModule } from 'primeng/tag';
import { MessageService } from 'primeng/api';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { User } from '../../core/auth/models';
import { ApiService } from '../../core/api/api.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ButtonModule, InputTextModule, PasswordModule, TagModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center justify-between mb-6">
      <h1 class="page-title">Settings</h1>
    </div>

    <div class="mb-6 flex flex-wrap gap-2">
      <a routerLink="/dashboard/settings/pixels" class="btn-ghost">
        <i class="pi pi-hashtag"></i><span>Tracking pixels</span>
      </a>
      <a routerLink="/dashboard/settings/utm-templates" class="btn-ghost">
        <i class="pi pi-tag"></i><span>UTM templates</span>
      </a>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <!-- Profile -->
      <form [formGroup]="profileForm" (ngSubmit)="saveProfile()" class="card flex flex-col gap-3">
        <h2 class="text-sm font-semibold text-slate-700">Profile</h2>
        <div>
          <label class="form-label" for="name">Name</label>
          <input pInputText id="name" formControlName="name" class="w-full" />
        </div>
        <div>
          <label class="form-label" for="email">Email</label>
          <input pInputText id="email" formControlName="email" class="w-full" type="email" />
        </div>
        <div class="flex items-center gap-2 mt-2">
          <span class="text-xs text-slate-500">Plan:</span>
          <p-tag [value]="plan()" severity="info" />
        </div>
        <div class="mt-2">
          <button pButton type="submit" class="btn-primary"
                  [disabled]="profileForm.invalid || savingProfile()"
                  [label]="savingProfile() ? 'Saving…' : 'Save profile'"></button>
        </div>
      </form>

      <!-- Password -->
      <form [formGroup]="passwordForm" (ngSubmit)="changePassword()" class="card flex flex-col gap-3">
        <h2 class="text-sm font-semibold text-slate-700">Change password</h2>
        <div>
          <label class="form-label" for="current">Current password</label>
          <p-password inputId="current" formControlName="current_password" styleClass="w-full"
                      inputStyleClass="w-full" [feedback]="false" [toggleMask]="true" />
        </div>
        <div>
          <label class="form-label" for="new">New password</label>
          <p-password inputId="new" formControlName="new_password" styleClass="w-full"
                      inputStyleClass="w-full" [toggleMask]="true" />
          @if (passwordForm.controls.new_password.touched && passwordForm.controls.new_password.invalid) {
            <small class="text-red-500">At least 8 characters.</small>
          }
        </div>
        <div class="mt-2">
          <button pButton type="submit" class="btn-primary"
                  [disabled]="passwordForm.invalid || savingPassword()"
                  [label]="savingPassword() ? 'Updating…' : 'Update password'"></button>
        </div>
      </form>
    </div>
  `,
})
export class SettingsComponent {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly toast = inject(MessageService);

  readonly user = this.auth.user;
  readonly plan = computed(() => this.user()?.plan ?? 'free');
  readonly savingProfile = signal(false);
  readonly savingPassword = signal(false);

  readonly profileForm = this.fb.group({
    name: this.fb.control(this.user()?.full_name ?? ''),
    email: this.fb.control(this.user()?.email ?? '', {
      validators: [Validators.required, Validators.email],
    }),
  });

  readonly passwordForm = this.fb.group({
    current_password: this.fb.control('', { validators: [Validators.required] }),
    new_password: this.fb.control('', { validators: [Validators.required, Validators.minLength(8)] }),
  });

  async saveProfile(): Promise<void> {
    if (this.profileForm.invalid) return;
    this.savingProfile.set(true);
    try {
      const updated = await firstValueFrom(
        this.api.patch<User>(
          '/v1/users/me',
          { full_name: this.profileForm.getRawValue().name, email: this.profileForm.getRawValue().email },
        ),
      );
      this.auth.user.set(updated);
      this.toast.add({ severity: 'success', summary: 'Profile saved' });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Save failed', detail: (e as Error).message });
    } finally {
      this.savingProfile.set(false);
    }
  }

  async changePassword(): Promise<void> {
    if (this.passwordForm.invalid) return;
    this.savingPassword.set(true);
    try {
      await firstValueFrom(this.api.post<void>('/v1/auth/password', this.passwordForm.getRawValue()));
      this.passwordForm.reset({ current_password: '', new_password: '' });
      this.toast.add({ severity: 'success', summary: 'Password updated' });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Update failed', detail: (e as Error).message });
    } finally {
      this.savingPassword.set(false);
    }
  }
}
