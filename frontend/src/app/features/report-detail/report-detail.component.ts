import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { DiffViewComponent } from '../../shared/components/diff-view/diff-view.component';
import { FileDownloadService, filenameFromContentDisposition } from '../../core/file-download.service';
import { AuditRunResponse } from '../../shared/interfaces/audit.interface';
import { RecommendationCardComponent } from './recommendation-card/recommendation-card.component';
import { ReportDetailApiService } from './report-detail-api.service';
import {
  EntityReportView,
  ExportState,
  FilterOption,
  ReportViewState,
  StatusFilter,
} from './report-detail.interface';
import { browserTimeZone, describeExportError } from './report-export';
import { ALWAYS_VISIBLE_FILTERS, STATUS_FILTER_LABELS } from './report-labels';
import { entityTrackKey, toEntityReportView } from './report-view.mapper';

@Component({
  selector: 'app-report-detail',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    DiffViewComponent,
    EmptyStateComponent,
    ErrorStateComponent,
    LoadingSkeletonComponent,
    RecommendationCardComponent,
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

  protected readonly entityTrackKey = entityTrackKey;

  protected readonly state = signal<ReportViewState>('loading');
  protected readonly run = signal<AuditRunResponse | null>(null);
  protected readonly statusFilter = signal<StatusFilter>('all');
  protected readonly exportState = signal<ExportState>('idle');
  protected readonly exportErrorMessage = signal('');

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
