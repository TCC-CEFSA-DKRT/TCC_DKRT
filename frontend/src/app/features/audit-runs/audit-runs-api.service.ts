import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import {
  AuditProgressResponse,
  AuditRunFilters,
  AuditRunSummaryResponse,
  PageResponse,
} from '../../shared/models/audit.models';

/** Fase 8, seção 4 — Audit Runs: lista com filtros + progresso em tempo
 * real. Reaproveita `GET /audits` (seção 0.1) e `GET /audits/{id}/progress`
 * (Fase 5) — nenhum endpoint novo. */
@Injectable({ providedIn: 'root' })
export class AuditRunsApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  listRuns(filters: AuditRunFilters): Observable<PageResponse<AuditRunSummaryResponse>> {
    let params = new HttpParams();
    if (filters.entity_type) params = params.set('entity_type', filters.entity_type);
    if (filters.status) params = params.set('status', filters.status);
    if (filters.started_after) params = params.set('started_after', filters.started_after);
    if (filters.started_before) params = params.set('started_before', filters.started_before);
    params = params.set('page', filters.page ?? 1).set('page_size', filters.page_size ?? 20);

    return this.http.get<PageResponse<AuditRunSummaryResponse>>(`${this.config.baseUrl}/audits`, {
      params,
    });
  }

  getProgress(runId: string): Observable<AuditProgressResponse> {
    return this.http.get<AuditProgressResponse>(
      `${this.config.baseUrl}/audits/${runId}/progress`
    );
  }
}
