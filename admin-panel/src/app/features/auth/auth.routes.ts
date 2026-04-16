import { Routes } from '@angular/router';
import { guestGuard } from '../../core/auth/auth.guard';

export const AUTH_ROUTES: Routes = [
  {
    path: 'login',
    canMatch: [guestGuard],
    loadComponent: () => import('./login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'register',
    canMatch: [guestGuard],
    loadComponent: () => import('./register.component').then((m) => m.RegisterComponent),
  },
];
