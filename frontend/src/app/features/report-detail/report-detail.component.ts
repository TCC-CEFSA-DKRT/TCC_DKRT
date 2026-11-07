import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TimeoutError } from 'rxjs';

import { FileDownloadService, filenameFromContentDisposition } from '../../core/file-download.service';

import { DiffViewComponent } from '../../shared/components/diff-view/diff-view.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import {
  AuditRunResponse,
  EntityReportResponse,
  RecommendationResponse,
  ViolationResponse,
  ViolationSeverity,
} from '../../shared/models/audit.models';
import { ReportDetailApiService } from './report-detail-api.service';
import {
  ACTION_LABELS,
  SEVERITY_GROUP_TITLES,
  SEVERITY_ORDER,
  STATUS_FILTER_LABELS,
  StatusFilter,
  ruleLabel,
} from './report-labels';

type ViewState = 'loading' | 'loaded' | 'empty' | 'error';
type ExportState = 'idle' | 'exporting' | 'error';

/** Recomendação do SLM pronta para exibição. Quando corresponde a uma
 * violação (`attachedToViolation`), o valor atual já aparece logo acima
 * em "Encontrado", então só a correção proposta é mostrada; caso
 * contrário, o diff compara o atributo com o `proposed_patch`. */
interface RecommendationView {
  actionLabel: string;
  rationale: string;
  confidencePercent: number;
  attachedToViolation: boolean;
  attributePath: string;
  proposedPatch: Record<string, unknown>;
  proposedPatchText: string;
}

interface ViolationView {
  violation: ViolationResponse;
  ruleLabel: string;
  recommendations: RecommendationView[];
}

interface SeverityGroupView {
  severity: ViolationSeverity;
  title: string;
  items: ViolationView[];
}

interface EntityReportView {
  report: EntityReportResponse;
  groups: SeverityGroupView[];
  /** Recomendações cujo `attribute_path` não corresponde a nenhuma violação. */
  otherRecommendations: RecommendationView[];
  /** O Nível 1 só roda quando há schema — sem modelo ou schema indisponível
   * não há validação nenhuma, e a nota de "só Nível 1" seria enganosa. */
  validated: boolean;
}

interface FilterOption {
  value: StatusFilter;
  label: string;
  count: number;
}

const ALWAYS_VISIBLE_FILTERS: StatusFilter[] = [
  'all',
  'conformant',
  'partial',
  'non_conformant',
  'no_model_found',
];

/** Fase 8, seção 5 + issue #22 — Report Detail: entidade a entidade, com
 * violações agrupadas por severidade, "encontrado × esperado" lado a lado,
 * a regra violada, a recomendação do SLM (com justificativa) junto da
 * violação que ela corrige, a origem do schema (ao vivo ou cache, com data)
 * e filtros por status. Objetivo (critério de aceite da #22): identificar,
 * sem abrir outra tela, qual atributo violou qual regra e o que corrigir. */
@Component({
  selector: 'app-report-detail',
  standalone: true,
  imports: [
    DatePipe,
    NgTemplateOutlet,
    RouterLink,
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
  private readonly downloads = inject(FileDownloadService);

  protected readonly state = signal<ViewState>('loading');
  protected readonly exportState = signal<ExportState>('idle');
  protected readonly exportErrorMessage = signal('');
  protected readonly run = signal<AuditRunResponse | null>(null);
  protected readonly statusFilter = signal<StatusFilter>('all');

  protected readonly totalReports = computed(() => this.run()?.reports.length ?? 0);

  protected readonly filterOptions = computed<FilterOption[]>(() => {
    const reports = this.run()?.reports ?? [];
    const countOf = (value: StatusFilter) =>
      value === 'all' ? reports.length : reports.filter((r) => r.status === value).length;
    const options = ALWAYS_VISIBLE_FILTERS.map((value) => ({
      value,
      label: STATUS_FILTER_LABELS[value],
      count: countOf(value),
    }));
    const unavailable = countOf('schema_unavailable');
    if (unavailable > 0) {
      options.push({
        value: 'schema_unavailable',
        label: STATUS_FILTER_LABELS.schema_unavailable,
        count: unavailable,
      });
    }
    return options;
  });

  protected readonly visibleReports = computed<EntityReportView[]>(() => {
    const filter = this.statusFilter();
    return (this.run()?.reports ?? [])
      .filter((report) => filter === 'all' || report.status === filter)
      .map((report) => toEntityReportView(report));
  });

  protected readonly selectedFilterLabel = computed(() =>
    STATUS_FILTER_LABELS[this.statusFilter()].toLowerCase()
  );

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
        this.statusFilter.set('all');
        this.state.set(run.reports.length === 0 ? 'empty' : 'loaded');
      },
      error: () => this.state.set('error'),
    });
  }

  protected onSelectFilter(filter: StatusFilter): void {
    this.statusFilter.set(filter);
  }

  /** Issue #23 — baixa o relatório em PDF, gerado no backend (ADR-0022).
   * Exporta sempre a auditoria inteira, independentemente do filtro de
   * status aplicado na tela. */
  protected onExportPdf(): void {
    const run = this.run();
    if (run === null || this.exportState() === 'exporting') {
      return;
    }
    this.exportState.set('exporting');
    this.exportErrorMessage.set('');
    this.api.exportPdf(run.id, browserTimeZone()).subscribe({
      next: (response) => {
        const filename =
          filenameFromContentDisposition(response.headers.get('Content-Disposition')) ??
          `relatorio-${run.id}.pdf`;
        if (response.body) {
          this.downloads.save(response.body, filename);
        }
        this.exportState.set('idle');
      },
      error: (error: unknown) => {
        this.exportErrorMessage.set(describeExportError(error));
        this.exportState.set('error');
      },
    });
  }
}

function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

function describeExportError(error: unknown): string {
  if (error instanceof TimeoutError) {
    return 'A geração do PDF demorou mais do que o esperado. Tente novamente em instantes.';
  }
  const status = error instanceof HttpErrorResponse ? error.status : -1;
  if (status === 0) {
    return 'Não foi possível conectar ao servidor do auditor. Verifique se a API está em execução.';
  }
  if (status === 404) {
    return 'Esta auditoria não foi encontrada. Atualize a página e tente novamente.';
  }
  return 'Não foi possível gerar o PDF. Tente novamente.';
}

function toEntityReportView(report: EntityReportResponse): EntityReportView {
  const pending = [...report.recommendations];
  const takeRecommendationsFor = (violation: ViolationResponse): RecommendationView[] => {
    const matched = pending.filter((rec) => rec.attribute_path === violation.attribute_path);
    for (const rec of matched) {
      pending.splice(pending.indexOf(rec), 1);
    }
    return matched.map((rec) => toRecommendationView(rec, true));
  };

  // Recomendações são associadas na ordem de severidade: se dois achados
  // apontam o mesmo atributo, a recomendação aparece junto do mais grave.
  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    title: SEVERITY_GROUP_TITLES[severity],
    items: report.violations
      .filter((violation) => violation.severity === severity)
      .map((violation) => ({
        violation,
        ruleLabel: ruleLabel(violation.rule),
        recommendations: takeRecommendationsFor(violation),
      })),
  })).filter((group) => group.items.length > 0);

  return {
    report,
    groups,
    otherRecommendations: pending.map((rec) => toRecommendationView(rec, false)),
    validated: report.status !== 'no_model_found' && report.status !== 'schema_unavailable',
  };
}

function toRecommendationView(
  rec: RecommendationResponse,
  attachedToViolation: boolean
): RecommendationView {
  return {
    actionLabel: ACTION_LABELS[rec.action] ?? rec.action,
    rationale: rec.rationale,
    confidencePercent: Math.round(rec.confidence * 100),
    attachedToViolation,
    attributePath: rec.attribute_path,
    proposedPatch: rec.proposed_patch,
    proposedPatchText: JSON.stringify(rec.proposed_patch, null, 2),
  };
}
