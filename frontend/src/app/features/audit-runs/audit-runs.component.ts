import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { interval } from 'rxjs';

import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import {
  AuditProgressResponse,
  AuditRunFilters,
  AuditRunSummaryResponse,
  RunStatus,
} from '../../shared/models/audit.models';
import { AuditRunsApiService } from './audit-runs-api.service';

type ViewState = 'loading' | 'loaded' | 'empty' | 'error';

const POLL_INTERVAL_MS = 5000;
const RUN_STATUS_OPTIONS: RunStatus[] = ['queued', 'running', 'completed', 'failed', 'partial'];

/** Fase 8, seção 4 — Audit Runs: lista com filtros (tipo, status, período)
 * refletidos na URL, progresso em tempo real dos runs em execução via
 * polling em `GET /audits/{id}/progress` (Fase 5, seção 4.3 permite
 * polling OU SSE — polling escolhido aqui por simplicidade, sem estado de
 * conexão a gerenciar no cliente). */
@Component({
  selector: 'app-audit-runs',
  standalone: true,
  imports: [
    DatePipe,
    FormsModule,
    RouterLink,
    EmptyStateComponent,
    ErrorStateComponent,
    LoadingSkeletonComponent,
    StatusBadgeComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './audit-runs.component.html',
  styleUrl: './audit-runs.component.scss',
})
export class AuditRunsComponent {
  private readonly api = inject(AuditRunsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly state = signal<ViewState>('loading');
  protected readonly runs = signal<AuditRunSummaryResponse[]>([]);
  protected readonly total = signal(0);
  protected readonly progressByRunId = signal<Partial<Record<string, AuditProgressResponse>>>({});
  protected readonly statusOptions = RUN_STATUS_OPTIONS;

  protected readonly filters = signal<AuditRunFilters>(this.filtersFromQueryParams());

  /** Ligados via `[(ngModel)]` ao formulário de filtros — estado de
   * rascunho do formulário, distinto de `filters()` (o filtro efetivamente
   * aplicado e refletido na URL). */
  protected entityTypeInput = this.filters().entity_type ?? '';
  protected statusInput: RunStatus | '' = this.filters().status ?? '';

  constructor() {
    this.load();
    // Fase 5, seção 4.2 — progresso via polling, não estado inventado no
    // cliente: cada tick busca o valor de verdade no backend.
    interval(POLL_INTERVAL_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.refreshProgress());
  }

  private filtersFromQueryParams(): AuditRunFilters {
    const params = this.route.snapshot.queryParamMap;
    return {
      entity_type: params.get('entity_type') ?? undefined,
      status: (params.get('status') as RunStatus | null) ?? undefined,
      started_after: params.get('started_after') ?? undefined,
      started_before: params.get('started_before') ?? undefined,
      page: params.get('page') ? Number(params.get('page')) : 1,
      page_size: params.get('page_size') ? Number(params.get('page_size')) : 20,
    };
  }

  protected load(): void {
    this.state.set('loading');
    this.api.listRuns(this.filters()).subscribe({
      next: (page) => {
        this.runs.set(page.items);
        this.total.set(page.total);
        this.state.set(page.items.length === 0 ? 'empty' : 'loaded');
      },
      error: () => this.state.set('error'),
    });
  }

  /** Aplica os filtros do formulário: escreve na URL (query params) — o
   * que permite compartilhar/recarregar a mesma visão (fase8.spec.md,
   * seção 4) — e recarrega a lista a partir dela. */
  protected applyFilters(next: AuditRunFilters): void {
    this.filters.set({ ...next, page: 1 });
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        entity_type: next.entity_type || null,
        status: next.status || null,
        started_after: next.started_after || null,
        started_before: next.started_before || null,
      },
      queryParamsHandling: 'merge',
    });
    this.load();
  }

  protected refreshProgress(): void {
    const runningRuns = this.runs().filter((r) => r.status === 'running');
    for (const run of runningRuns) {
      this.api.getProgress(run.id).subscribe((progress) => {
        this.progressByRunId.update((current) => ({ ...current, [run.id]: progress }));
      });
    }
  }
}
