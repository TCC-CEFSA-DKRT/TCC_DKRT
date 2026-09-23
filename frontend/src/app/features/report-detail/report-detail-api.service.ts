import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import { AuditRunResponse } from '../../shared/models/audit.models';

/** Fase 8, seção 5 — Report Detail. Reaproveita `GET /audits/{run_id}`
 * (Fase 4), que já traz `reports[]` completo (violações + recomendações,
 * Fase 7) — sem endpoint novo. */
@Injectable({ providedIn: 'root' })
export class ReportDetailApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  getRun(runId: string): Observable<AuditRunResponse> {
    return this.http.get<AuditRunResponse>(`${this.config.baseUrl}/audits/${runId}`);
  }
}
