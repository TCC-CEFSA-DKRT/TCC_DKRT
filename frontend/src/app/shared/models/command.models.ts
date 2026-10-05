/** Espelha `InterpretAuditRequest`/`InterpretAuditResponse` (backend). */
export interface InterpretAuditRequest {
  command_text: string;
}

export interface InterpretAuditResponse {
  intent: 'audit' | 'discovery';
  entity_type: string | null;
  entity_id: string | null;
  confidence: number;
  raw_command: string;
  discovered_types: string[] | null;
  broker_reachable: boolean | null;
}
