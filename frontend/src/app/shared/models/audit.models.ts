/**
 * DTOs espelhando `src/auditor/interfaces/rest/schemas.py` (backend) campo
 * a campo — ver fase8.spec.md, seção 1: "qualquer divergência de nome/tipo
 * é bug de contrato, não estilo". Enums espelham os `str, Enum` do domínio
 * (valores exatos, minúsculos, ver `violation.py`/`recommendation.py`/
 * `conformance_status.py`/`audit_run.py`).
 */

export type ViolationSeverity = 'error' | 'warning' | 'info';

export type DetectionSource = 'structural' | 'semantic';

export type ConformanceStatus =
  | 'conformant'
  | 'partial'
  | 'non_conformant'
  | 'no_model_found'
  | 'schema_unavailable';

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'partial' | 'no_entities_found';

export type RecommendationAction =
  | 'rename_attribute'
  | 'add_missing_attribute'
  | 'fix_type'
  | 'fix_format';

export interface ViolationResponse {
  attribute_path: string;
  severity: ViolationSeverity;
  rule: string;
  expected: string | null;
  found: string | null;
  message: string;
  detected_by: DetectionSource;
}

export interface RecommendationResponse {
  attribute_path: string;
  action: RecommendationAction;
  proposed_patch: Record<string, unknown>;
  rationale: string;
  confidence: number;
}

export interface EntityReportResponse {
  entity_id: string;
  entity_type: string;
  status: ConformanceStatus;
  violations: ViolationResponse[];
  recommendations: RecommendationResponse[];
  semantic_analysis_skipped: boolean;
}

export interface RunSummaryResponse {
  total_entities: number;
  conformant_count: number;
  non_conformant_count: number;
  partial_count: number;
  no_model_count: number;
  schema_unavailable_count: number;
}

export interface AuditRunResponse {
  id: string;
  status: RunStatus;
  entity_type: string | null;
  summary: RunSummaryResponse;
  started_at: string;
  finished_at: string | null;
  broker_url: string;
  reports: EntityReportResponse[];
}

export interface AuditRunSummaryResponse {
  id: string;
  entity_type: string | null;
  status: RunStatus;
  summary: RunSummaryResponse;
  started_at: string;
  finished_at: string | null;
  broker_url: string;
  total_entities_discovered: number | null;
  failure_reason: string | null;
}

export interface PageResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
}

export interface AuditProgressResponse {
  status: string;
  processed: number;
  total: number | null;
}

export interface AuditCreateRequest {
  entity_type: string | null;
  entity_id: string | null;
}

export interface AuditCreateResponse {
  run_id: string;
  status: string;
}

/** Filtros de `GET /audits` (fase8.spec.md, seção 0.1) — refletidos na URL
 * (query params) para permitir compartilhar/recarregar a mesma visão. */
export interface AuditRunFilters {
  entity_type?: string;
  status?: RunStatus;
  started_after?: string;
  started_before?: string;
  page?: number;
  page_size?: number;
}
