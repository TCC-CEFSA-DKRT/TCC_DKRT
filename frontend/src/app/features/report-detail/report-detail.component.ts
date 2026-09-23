import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { ActivatedRoute } from '@angular/router';

import { DiffViewComponent } from '../../shared/components/diff-view/diff-view.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { AuditRunResponse, ViolationResponse, ViolationSeverity } from '../../shared/models/audit.models';
import { ReportDetailApiService } from './report-detail-api.service';

type ViewState = 'loading' | 'loaded' | 'empty' | 'error';

const SEVERITY_ORDER: ViolationSeverity[] = ['error', 'warning', 'info'];

/** Fase 8, seção 5 — Report Detail: entidade a entidade, violações
 * agrupadas por severidade, diff visual, recomendação do SLM. */
@Component({
  selector: 'app-report-detail',
  standalone: true,
  imports: [
    DecimalPipe,
    DiffViewComponent,
    EmptyStateComponent,
    ErrorStateComponent,
    LoadingSkeletonComponent,
    StatusBadgeComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './report-detail.component.html',
  styleUrl: './report-detail.component.scss',
})
export class ReportDetailComponent {
  private readonly api = inject(ReportDetailApiService);
  private readonly route = inject(ActivatedRoute);

  protected readonly state = signal<ViewState>('loading');
  protected readonly run = signal<AuditRunResponse | null>(null);
  protected readonly severityOrder = SEVERITY_ORDER;

  constructor() {
    this.load();
  }

  protected load(): void {
    this.state.set('loading');
    const runId = this.route.snapshot.paramMap.get('runId');
    if (!runId) {
      this.state.set('error');
      return;
    }
    this.api.getRun(runId).subscribe({
      next: (run) => {
        this.run.set(run);
        this.state.set(run.reports.length === 0 ? 'empty' : 'loaded');
      },
      error: () => this.state.set('error'),
    });
  }

  /** Violações de um relatório, agrupadas por severidade (Fase 8, seção 5)
   * — cada grupo já vem com a origem (`detected_by`) de cada violação
   * preservada, nunca escondida numa lista homogênea. */
  protected violationsBySeverity(
    violations: ViolationResponse[]
  ): { severity: ViolationSeverity; items: ViolationResponse[] }[] {
    return SEVERITY_ORDER.map((severity) => ({
      severity,
      items: violations.filter((v) => v.severity === severity),
    })).filter((group) => group.items.length > 0);
  }

  protected readonly totalReports = computed(() => this.run()?.reports.length ?? 0);
}
