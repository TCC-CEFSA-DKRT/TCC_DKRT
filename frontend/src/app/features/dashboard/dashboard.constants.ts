import { RunSummaryResponse } from '../../shared/models/audit.models';
import { StatusSegmentDefinition } from './dashboard.models';

export const EMPTY_SUMMARY: RunSummaryResponse = {
  total_entities: 0,
  conformant_count: 0,
  non_conformant_count: 0,
  partial_count: 0,
  no_model_count: 0,
  schema_unavailable_count: 0,
};

export const STATUS_SEGMENTS: readonly StatusSegmentDefinition[] = [
  { key: 'conformant_count', label: 'Conformes', cssModifier: 'conformant' },
  { key: 'partial_count', label: 'Parciais', cssModifier: 'partial' },
  { key: 'non_conformant_count', label: 'Não conformes', cssModifier: 'non-conformant' },
  { key: 'no_model_count', label: 'Sem modelo', cssModifier: 'no-model' },
  { key: 'schema_unavailable_count', label: 'Schema indisponível', cssModifier: 'schema-unavailable' },
];

export const TIMELINE_SEGMENTS: readonly StatusSegmentDefinition[] = STATUS_SEGMENTS.slice(0, 3);

export const UNTYPED_RUN_LABEL = '(sem tipo)';
