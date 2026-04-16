import { Routes } from '@angular/router';

export const API_KEYS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./api-keys.component').then((m) => m.ApiKeysComponent),
  },
];
