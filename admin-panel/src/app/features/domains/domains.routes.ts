import { Routes } from '@angular/router';

export const DOMAINS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./domains.component').then((m) => m.DomainsComponent),
  },
];
