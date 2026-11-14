import { RunSummaryResponse } from '../../shared/models/audit.models';

export type DashboardViewState = 'loading' | 'loaded' | 'empty' | 'error';

export type SummaryStatusKey =
  | 'conformant_count'
  | 'partial_count'
  | 'non_conformant_count'
  | 'no_model_count'
  | 'schema_unavailable_count';

export interface StatusSegmentDefinition {
  key: SummaryStatusKey;
  label: string;
  cssModifier: string;
}

export interface CategoryAggregate {
  entityType: string;
  summary: RunSummaryResponse;
  runCount: number;
}

export interface StatusSegment {
  label: string;
  cssModifier: string;
  count: number;
  percent: number;
}

export interface SummaryTile {
  label: string;
  value: string;
  hint: string;
  tone: 'neutral' | 'good' | 'bad';
}

export interface RankingBar {
  entityType: string;
  count: number;
  percentOfMax: number;
}

export interface TimelineColumn {
  id: string;
  startedAt: string;
  total: number;
  segments: StatusSegment[];
  heightPercent: number;
}
