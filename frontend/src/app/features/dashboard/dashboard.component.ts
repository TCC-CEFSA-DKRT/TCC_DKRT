import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { AuditRunSummaryResponse } from '../../shared/models/audit.models';
import { DashboardApiService } from './dashboard-api.service';
import { STATUS_SEGMENTS, TIMELINE_SEGMENTS } from './dashboard.constants';
import {
  aggregateByType,
  describeColumn,
  describeSegments,
  entitiesWithViolation,
  rankingBars,
  statusSegments,
  summaryTiles,
  timelineColumns,
} from './dashboard-charts';
import { CategoryAggregate, DashboardViewState } from './dashboard.models';

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

  protected readonly statusLegend = STATUS_SEGMENTS;
  protected readonly timelineLegend = TIMELINE_SEGMENTS;
  protected readonly statusSegments = statusSegments;
  protected readonly entitiesWithViolation = entitiesWithViolation;
  protected readonly describeSegments = describeSegments;
  protected readonly describeColumn = describeColumn;

  protected readonly state = signal<DashboardViewState>('loading');
  protected readonly runs = signal<AuditRunSummaryResponse[]>([]);
  protected readonly timeSeries = signal<AuditRunSummaryResponse[]>([]);
  protected readonly selectedEntityType = signal<string | null>(null);

  protected readonly categoryAggregates = computed<CategoryAggregate[]>(() =>
    aggregateByType(this.runs())
  );

  protected readonly typesRankedByViolations = computed<CategoryAggregate[]>(() =>
    [...this.categoryAggregates()].sort(
      (a, b) => entitiesWithViolation(b.summary) - entitiesWithViolation(a.summary)
    )
  );

  protected readonly tiles = computed(() => summaryTiles(this.runs()));
  protected readonly ranking = computed(() => rankingBars(this.categoryAggregates()));
  protected readonly timeline = computed(() => timelineColumns(this.timeSeries()));

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
      error: () => this.timeSeries.set([]),
    });
  }
}
