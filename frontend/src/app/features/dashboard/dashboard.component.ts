import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { AuditRunSummaryResponse, RunSummaryResponse } from '../../shared/models/audit.models';
import { DashboardApiService } from './dashboard-api.service';

type ViewState = 'loading' | 'loaded' | 'empty' | 'error';

interface CategoryAggregate {
  entityType: string;
  summary: RunSummaryResponse;
  runCount: number;
}

const EMPTY_SUMMARY: RunSummaryResponse = {
  total_entities: 0,
  conformant_count: 0,
  non_conformant_count: 0,
  partial_count: 0,
  no_model_count: 0,
  schema_unavailable_count: 0,
};

/** Fase 8, seção 3 — Dashboard: conformidade por tenant/categoria,
 * evolução no tempo, tipos com mais violações. */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [DatePipe, EmptyStateComponent, ErrorStateComponent, LoadingSkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent {
  private readonly api = inject(DashboardApiService);

  protected readonly state = signal<ViewState>('loading');
  protected readonly runs = signal<AuditRunSummaryResponse[]>([]);
  protected readonly timeSeries = signal<AuditRunSummaryResponse[]>([]);
  protected readonly selectedEntityType = signal<string | null>(null);

  /** Agregação por categoria — soma direta dos campos de `RunSummary` de
   * cada run (fase8.spec.md, seção 3: "a agregação por categoria reflete
   * exatamente as contagens de RunSummary somadas — nenhum recálculo
   * divergente no frontend"). Nunca reconta violações a partir de
   * `reports[]` (que nem está disponível em `AuditRunSummaryResponse`). */
  protected readonly categoryAggregates = computed<CategoryAggregate[]>(() => {
    const byType = new Map<string, CategoryAggregate>();
    for (const run of this.runs()) {
      const key = run.entity_type ?? '(sem tipo)';
      const existing = byType.get(key) ?? {
        entityType: key,
        summary: { ...EMPTY_SUMMARY },
        runCount: 0,
      };
      existing.summary = {
        total_entities: existing.summary.total_entities + run.summary.total_entities,
        conformant_count: existing.summary.conformant_count + run.summary.conformant_count,
        non_conformant_count:
          existing.summary.non_conformant_count + run.summary.non_conformant_count,
        partial_count: existing.summary.partial_count + run.summary.partial_count,
        no_model_count: existing.summary.no_model_count + run.summary.no_model_count,
        schema_unavailable_count:
          existing.summary.schema_unavailable_count + run.summary.schema_unavailable_count,
      };
      existing.runCount += 1;
      byType.set(key, existing);
    }
    return Array.from(byType.values());
  });

  /** Tipos com mais violações (não-conformidades + parciais), ordenado
   * decrescente — dado bruto direto de `categoryAggregates`, sem nova
   * fonte de verdade. */
  protected readonly typesRankedByViolations = computed<CategoryAggregate[]>(() =>
    [...this.categoryAggregates()].sort((a, b) => {
      const violationsA = a.summary.non_conformant_count + a.summary.partial_count;
      const violationsB = b.summary.non_conformant_count + b.summary.partial_count;
      return violationsB - violationsA;
    })
  );

  constructor() {
    this.load();
  }

  protected load(): void {
    this.state.set('loading');
    this.api.listRunsForAggregation().subscribe({
      next: (page) => {
        this.runs.set(page.items);
        if (page.items.length === 0) {
          this.state.set('empty');
          return;
        }
        this.state.set('loaded');
        const firstType = page.items.find((r) => r.entity_type)?.entity_type ?? null;
        this.selectedEntityType.set(firstType);
        if (firstType) {
          this.loadTimeSeries(firstType);
        }
      },
      error: () => this.state.set('error'),
    });
  }

  protected selectEntityType(entityType: string): void {
    this.selectedEntityType.set(entityType);
    this.loadTimeSeries(entityType);
  }

  private loadTimeSeries(entityType: string): void {
    this.api.summaryOverTime(entityType).subscribe({
      next: (series) => this.timeSeries.set(series),
      // A evolução no tempo é um complemento do dashboard — uma falha
      // isolada aqui não derruba a tela inteira (que já mostra a
      // agregação por categoria com sucesso); só limpa a série.
      error: () => this.timeSeries.set([]),
    });
  }
}
