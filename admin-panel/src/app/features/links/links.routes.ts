import { Routes } from '@angular/router';

export const LINKS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./list.component').then((m) => m.LinksListComponent),
  },
  {
    path: 'new',
    loadComponent: () => import('./create.component').then((m) => m.LinkCreateComponent),
  },
  {
    path: ':id',
    loadComponent: () => import('./detail.component').then((m) => m.LinkDetailComponent),
  },
];
