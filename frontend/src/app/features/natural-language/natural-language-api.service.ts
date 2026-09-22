import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import { AuditCreateRequest, AuditCreateResponse } from '../../shared/models/audit.models';
import { InterpretAuditRequest, InterpretAuditResponse } from '../../shared/models/command.models';

/** Fase 8, seção 6 — Natural Language. `interpret()` chama `POST
 * /audits/interpret` (seção 0.3, nunca dispara auditoria); `confirmAudit()`
 * chama o `POST /audits` já existente (Fase 5) — chamado só depois da
 * confirmação humana explícita, nunca a partir de `interpret()` sozinho. */
@Injectable({ providedIn: 'root' })
export class NaturalLanguageApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  interpret(commandText: string): Observable<InterpretAuditResponse> {
    const body: InterpretAuditRequest = { command_text: commandText };
    return this.http.post<InterpretAuditResponse>(
      `${this.config.baseUrl}/audits/interpret`,
      body
    );
  }

  confirmAudit(entityType: string | null, entityId: string | null): Observable<AuditCreateResponse> {
    const body: AuditCreateRequest = { entity_type: entityType, entity_id: entityId };
    return this.http.post<AuditCreateResponse>(`${this.config.baseUrl}/audits`, body);
  }
}
