import { Routes } from '@angular/router';

export const DASHBOARD_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./overview.component').then((m) => m.OverviewComponent),
  },
  {
    path: 'links',
    loadChildren: () => import('../links/links.routes').then((m) => m.LINKS_ROUTES),
  },
  {
    path: 'domains',
    loadChildren: () => import('../domains/domains.routes').then((m) => m.DOMAINS_ROUTES),
  },
  {
    path: 'api-keys',
    loadChildren: () => import('../api-keys/api-keys.routes').then((m) => m.API_KEYS_ROUTES),
  },
  {
    path: 'webhooks',
    loadChildren: () => import('../webhooks/webhooks.routes').then((m) => m.WEBHOOKS_ROUTES),
  },
  {
    path: 'settings',
    loadChildren: () => import('../settings/settings.routes').then((m) => m.SETTINGS_ROUTES),
  },
];
