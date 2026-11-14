import { AuditRunSummaryResponse, RunSummaryResponse } from '../../shared/models/audit.models';
import {
  aggregateByType,
  describeSegments,
  rankingBars,
  statusSegments,
  summaryTiles,
  timelineColumns,
} from './dashboard-charts';

function summary(conformant: number, partial: number, nonConformant: number, noModel = 0): RunSummaryResponse {
  return {
    total_entities: conformant + partial + nonConformant + noModel,
    conformant_count: conformant,
    partial_count: partial,
    non_conformant_count: nonConformant,
    no_model_count: noModel,
    schema_unavailable_count: 0,
  };
}

function run(id: string, entityType: string | null, s: RunSummaryResponse): AuditRunSummaryResponse {
  return {
    id,
    entity_type: entityType,
    status: 'completed',
    summary: s,
    started_at: '2026-11-14T13:05:00Z',
    finished_at: '2026-11-14T13:06:00Z',
    broker_url: 'http://orion:1026',
    total_entities_discovered: s.total_entities,
    failure_reason: null,
  };
}

describe('dashboard-charts', () => {
  const runs = [
    run('1', 'Streetlight', summary(1, 1, 2)),
    run('2', 'Streetlight', summary(3, 0, 1)),
    run('3', 'AirQualityObserved', summary(9, 2, 3)),
    run('4', null, summary(0, 0, 0, 2)),
  ];

  it('sums every RunSummary field per entity type', () => {
    const [streetlight, air, untyped] = aggregateByType(runs);

    expect(streetlight.entityType).toBe('Streetlight');
    expect(streetlight.runCount).toBe(2);
    expect(streetlight.summary).toEqual(summary(4, 1, 3));
    expect(air.summary.total_entities).toBe(14);
    expect(untyped.entityType).toBe('(sem tipo)');
  });

  it('builds the summary tiles from all runs', () => {
    const tiles = summaryTiles(runs);

    expect(tiles.map((tile) => tile.value)).toEqual(['4', '24', '54%', '9']);
    expect(tiles[2].hint).toBe('13 de 24 entidades');
  });

  it('shows a dash instead of a percentage when no entity was audited', () => {
    expect(summaryTiles([run('x', 'A', summary(0, 0, 0))])[2].value).toBe('—');
  });

  it('splits a summary into status segments that add up to 100%', () => {
    const segments = statusSegments(summary(2, 1, 1));

    expect(segments.map((segment) => segment.count)).toEqual([2, 1, 1, 0, 0]);
    expect(segments.reduce((total, segment) => total + segment.percent, 0)).toBeCloseTo(100);
    expect(describeSegments(segments)).toBe('Conformes: 2, Parciais: 1, Não conformes: 1');
  });

  it('ranks types by entities with violation, scaled to the largest', () => {
    const bars = rankingBars(aggregateByType(runs));

    expect(bars.map((bar) => [bar.entityType, bar.count])).toEqual([
      ['AirQualityObserved', 5],
      ['Streetlight', 4],
      ['(sem tipo)', 0],
    ]);
    expect(bars[0].percentOfMax).toBe(100);
    expect(bars[1].percentOfMax).toBe(80);
  });

  it('scales the timeline columns to the tallest run', () => {
    const columns = timelineColumns([run('a', 'S', summary(1, 1, 2)), run('b', 'S', summary(4, 2, 2))]);

    expect(columns.map((column) => column.total)).toEqual([4, 8]);
    expect(columns.map((column) => column.heightPercent)).toEqual([50, 100]);
    expect(columns[0].segments.map((segment) => segment.label)).toEqual([
      'Conformes',
      'Parciais',
      'Não conformes',
    ]);
  });
});
