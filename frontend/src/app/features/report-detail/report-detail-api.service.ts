import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, timeout } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import { AuditRunResponse } from '../../shared/models/audit.models';

/** Issue #23 — limite de espera do PDF no navegador. Um relatório com 500+
 * entidades leva poucos segundos no backend; o limite só existe para o
 * botão nunca ficar "gerando" para sempre se a API travar. */
export const EXPORT_PDF_TIMEOUT_MS = 120_000;

/** Fase 8, seção 5 — Report Detail. Reaproveita `GET /audits/{run_id}`
 * (Fase 4), que já traz `reports[]` completo (violações + recomendações,
 * Fase 7) — sem endpoint novo. Issue #23: `exportPdf()` baixa o mesmo
 * relatório em PDF, gerado no backend (ADR-0021). */
@Injectable({ providedIn: 'root' })
export class ReportDetailApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  getRun(runId: string): Observable<AuditRunResponse> {
    return this.http.get<AuditRunResponse>(`${this.config.baseUrl}/audits/${runId}`);
  }

  /** `timeZone` é o fuso do navegador (ex.: "America/Sao_Paulo"): as
   * datas do PDF saem no horário de quem exportou. */
  exportPdf(runId: string, timeZone: string): Observable<HttpResponse<Blob>> {
    return this.http
      .get(`${this.config.baseUrl}/audits/${runId}/report.pdf`, {
        params: new HttpParams().set('tz', timeZone),
        responseType: 'blob',
        observe: 'response',
      })
      .pipe(timeout(EXPORT_PDF_TIMEOUT_MS));
  }
}
