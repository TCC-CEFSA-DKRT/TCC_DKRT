import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { DiffViewComponent } from '../../shared/components/diff-view/diff-view.component';
import { AuditRunResponse } from '../../shared/models/audit.models';
import { RecommendationCardComponent } from './recommendation-card/recommendation-card.component';
import { ReportDetailApiService } from './report-detail-api.service';
import {
  EntityReportView,
  FilterOption,
  ReportViewState,
  StatusFilter,
} from './report-detail.models';
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

  protected readonly entityTrackKey = entityTrackKey;

  protected readonly state = signal<ReportViewState>('loading');
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
}
