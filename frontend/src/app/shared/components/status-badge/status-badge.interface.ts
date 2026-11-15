export type BadgeKind =
  | 'conformant'
  | 'partial'
  | 'non_conformant'
  | 'no_model_found'
  | 'schema_unavailable'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'no_entities_found'
  | 'error'
  | 'warning'
  | 'info';

export interface BadgeStyle {
  label: string;
  colorVar: string;
}
