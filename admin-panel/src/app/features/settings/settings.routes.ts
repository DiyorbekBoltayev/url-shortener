import { Routes } from '@angular/router';

export const SETTINGS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./settings.component').then((m) => m.SettingsComponent),
  },
  {
    path: 'pixels',
    loadComponent: () => import('./pixels.component').then((m) => m.PixelsSettingsComponent),
  },
  {
    path: 'utm-templates',
    loadComponent: () =>
      import('./utm-templates.component').then((m) => m.UtmTemplatesSettingsComponent),
  },
];
