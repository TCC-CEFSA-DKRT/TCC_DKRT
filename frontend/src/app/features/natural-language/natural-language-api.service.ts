import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, timeout } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import { AuditCreateRequest, AuditCreateResponse } from '../../shared/models/audit.models';
import { InterpretAuditRequest, InterpretAuditResponse } from '../../shared/models/command.models';

/** Issue #21 — limite de espera no navegador. O backend já desiste do
 * Ollama em 60 s e devolve `interpreter_available: false`; este limite só
 * existe para a tela nunca ficar "carregando" para sempre se a própria API
 * travar. */
export const INTERPRET_TIMEOUT_MS = 90_000;
export const CONFIRM_TIMEOUT_MS = 30_000;

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
    return this.http
      .post<InterpretAuditResponse>(`${this.config.baseUrl}/audits/interpret`, body)
      .pipe(timeout(INTERPRET_TIMEOUT_MS));
  }

  confirmAudit(entityType: string | null, entityId: string | null): Observable<AuditCreateResponse> {
    const body: AuditCreateRequest = { entity_type: entityType, entity_id: entityId };
    return this.http
      .post<AuditCreateResponse>(`${this.config.baseUrl}/audits`, body)
      .pipe(timeout(CONFIRM_TIMEOUT_MS));
  }
}
