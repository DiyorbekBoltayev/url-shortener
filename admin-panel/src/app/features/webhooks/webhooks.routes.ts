import { Routes } from '@angular/router';

export const WEBHOOKS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./webhooks.component').then((m) => m.WebhooksComponent),
  },
];
