import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, timeout } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import { AuditRunResponse } from '../../shared/interfaces/audit.interface';
import { EXPORT_PDF_TIMEOUT_MS } from './report-labels';

@Injectable({ providedIn: 'root' })
export class ReportDetailApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  getRun(runId: string): Observable<AuditRunResponse> {
    return this.http.get<AuditRunResponse>(`${this.config.baseUrl}/audits/${runId}`);
  }

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
