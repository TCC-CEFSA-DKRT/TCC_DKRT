import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import { AuditRunSummaryResponse, PageResponse } from '../../shared/models/audit.models';

/** Fase 8, seção 3 — dados do Dashboard. Reaproveita os dois endpoints da
 * seção 0 (`GET /audits` para a agregação por tenant/categoria, `GET
 * /audits/summary-over-time` para a evolução no tempo de um tipo) — sem
 * endpoint próprio, sem recálculo do backend no cliente além de somar o
 * que já vem pronto em `RunSummary`. */
@Injectable({ providedIn: 'root' })
export class DashboardApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  /** Traz até `pageSize` runs mais recentes do tenant — base para a
   * agregação por categoria e o ranking de "tipos com mais violações".
   * `pageSize` grande o bastante para não paginar no caso comum de uso
   * (dezenas de runs); paginação de verdade fica na tela Audit Runs. */
  listRunsForAggregation(pageSize = 200): Observable<PageResponse<AuditRunSummaryResponse>> {
    const params = new HttpParams().set('page', 1).set('page_size', pageSize);
    return this.http.get<PageResponse<AuditRunSummaryResponse>>(
      `${this.config.baseUrl}/audits`,
      { params }
    );
  }

  summaryOverTime(entityType: string): Observable<AuditRunSummaryResponse[]> {
    const params = new HttpParams().set('entity_type', entityType);
    return this.http.get<AuditRunSummaryResponse[]>(
      `${this.config.baseUrl}/audits/summary-over-time`,
      { params }
    );
  }
}
