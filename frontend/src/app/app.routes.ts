import { Routes } from '@angular/router';

/** Roteamento lazy por feature (fase8.spec.md, seção 1) — cada rota carrega
 * seu componente standalone só quando visitada, nenhum NgModule. */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
  },
  {
    path: 'audit-runs',
    loadComponent: () =>
      import('./features/audit-runs/audit-runs.component').then((m) => m.AuditRunsComponent),
  },
  {
    path: 'audit-runs/:runId',
    loadComponent: () =>
      import('./features/report-detail/report-detail.component').then(
        (m) => m.ReportDetailComponent
      ),
  },
  {
    path: 'natural-language',
    loadComponent: () =>
      import('./features/natural-language/natural-language.component').then(
        (m) => m.NaturalLanguageComponent
      ),
  },
  {
    path: 'catalog',
    loadComponent: () =>
      import('./features/catalog/catalog.component').then((m) => m.CatalogComponent),
  },
  { path: '**', redirectTo: 'dashboard' },
];
