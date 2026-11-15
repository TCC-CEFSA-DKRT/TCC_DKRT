import {
  ConformanceStatus,
  EntityReportResponse,
  ViolationResponse,
  ViolationSeverity,
} from '../../shared/models/audit.models';

export type ReportViewState = 'loading' | 'loaded' | 'empty' | 'error';

export type ExportState = 'idle' | 'exporting' | 'error';

export type StatusFilter = 'all' | ConformanceStatus;

export interface RecommendationView {
  actionLabel: string;
  rationale: string;
  confidencePercent: number;
  attachedToViolation: boolean;
  attributePath: string;
  proposedPatch: Record<string, unknown>;
  proposedPatchText: string;
}

export interface ViolationView {
  violation: ViolationResponse;
  ruleLabel: string;
  recommendations: RecommendationView[];
}

export interface SeverityGroupView {
  severity: ViolationSeverity;
  title: string;
  items: ViolationView[];
}

export interface EntityReportView {
  report: EntityReportResponse;
  groups: SeverityGroupView[];
  otherRecommendations: RecommendationView[];
  validated: boolean;
}

export interface FilterOption {
  value: StatusFilter;
  label: string;
  count: number;
}
