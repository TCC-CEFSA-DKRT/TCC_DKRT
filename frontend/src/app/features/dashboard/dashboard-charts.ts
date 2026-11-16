import { AuditRunSummaryResponse, RunSummaryResponse } from '../../shared/interfaces/audit.interface';
import { EMPTY_SUMMARY, STATUS_SEGMENTS, TIMELINE_SEGMENTS, UNTYPED_RUN_LABEL } from './dashboard.constants';
import {
  CategoryAggregate,
  RankingBar,
  StatusSegment,
  StatusSegmentDefinition,
  SummaryTile,
  TimelineColumn,
} from './dashboard.interface';

export function addSummaries(a: RunSummaryResponse, b: RunSummaryResponse): RunSummaryResponse {
  return {
    total_entities: a.total_entities + b.total_entities,
    conformant_count: a.conformant_count + b.conformant_count,
    non_conformant_count: a.non_conformant_count + b.non_conformant_count,
    partial_count: a.partial_count + b.partial_count,
    no_model_count: a.no_model_count + b.no_model_count,
    schema_unavailable_count: a.schema_unavailable_count + b.schema_unavailable_count,
  };
}

export function aggregateByType(runs: AuditRunSummaryResponse[]): CategoryAggregate[] {
  const byType = new Map<string, CategoryAggregate>();
  for (const run of runs) {
    const key = run.entity_type ?? UNTYPED_RUN_LABEL;
    const existing = byType.get(key) ?? { entityType: key, summary: { ...EMPTY_SUMMARY }, runCount: 0 };
    byType.set(key, {
      entityType: key,
      summary: addSummaries(existing.summary, run.summary),
      runCount: existing.runCount + 1,
    });
  }
  return Array.from(byType.values());
}

export function entitiesWithViolation(summary: RunSummaryResponse): number {
  return summary.non_conformant_count + summary.partial_count;
}

export function statusSegments(
  summary: RunSummaryResponse,
  definitions: readonly StatusSegmentDefinition[] = STATUS_SEGMENTS
): StatusSegment[] {
  const total = definitions.reduce((sum, definition) => sum + summary[definition.key], 0);
  return definitions.map((definition) => ({
    label: definition.label,
    cssModifier: definition.cssModifier,
    count: summary[definition.key],
    percent: total ? (summary[definition.key] / total) * 100 : 0,
  }));
}

export function percentLabel(part: number, total: number): string {
  return total ? `${Math.round((part / total) * 100)}%` : '—';
}

export function summaryTiles(runs: AuditRunSummaryResponse[]): SummaryTile[] {
  const total = runs.map((run) => run.summary).reduce(addSummaries, { ...EMPTY_SUMMARY });
  const withViolation = entitiesWithViolation(total);
  return [
    { label: 'Auditorias', value: String(runs.length), hint: 'execuções registradas', tone: 'neutral' },
    { label: 'Entidades auditadas', value: String(total.total_entities), hint: 'somando todas as auditorias', tone: 'neutral' },
    {
      label: 'Conformes',
      value: percentLabel(total.conformant_count, total.total_entities),
      hint: `${total.conformant_count} de ${total.total_entities} entidades`,
      tone: 'good',
    },
    {
      label: 'Com violação',
      value: String(withViolation),
      hint: 'entidades não conformes ou parciais',
      tone: 'bad',
    },
  ];
}

export function rankingBars(categories: CategoryAggregate[]): RankingBar[] {
  const ranked = [...categories].sort(
    (a, b) => entitiesWithViolation(b.summary) - entitiesWithViolation(a.summary)
  );
  const max = Math.max(1, ...ranked.map((category) => entitiesWithViolation(category.summary)));
  return ranked.map((category) => ({
    entityType: category.entityType,
    count: entitiesWithViolation(category.summary),
    percentOfMax: (entitiesWithViolation(category.summary) / max) * 100,
  }));
}

export function timelineColumns(series: AuditRunSummaryResponse[]): TimelineColumn[] {
  const totals = series.map((run) =>
    TIMELINE_SEGMENTS.reduce((sum, definition) => sum + run.summary[definition.key], 0)
  );
  const max = Math.max(1, ...totals);
  return series.map((run, index) => ({
    id: run.id,
    startedAt: run.started_at,
    total: totals[index],
    segments: statusSegments(run.summary, TIMELINE_SEGMENTS),
    heightPercent: (totals[index] / max) * 100,
  }));
}

export function describeSegments(segments: StatusSegment[]): string {
  return segments
    .filter((segment) => segment.count > 0)
    .map((segment) => `${segment.label}: ${segment.count}`)
    .join(', ');
}

export function describeColumn(column: TimelineColumn): string {
  const when = new Date(column.startedAt).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${when} — ${describeSegments(column.segments)}`;
}
