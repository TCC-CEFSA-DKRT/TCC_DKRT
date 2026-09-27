/** Espelha `InterpretAuditRequest`/`InterpretAuditResponse` (backend). */
export interface InterpretAuditRequest {
  command_text: string;
}

export interface InterpretAuditResponse {
  entity_type: string | null;
  entity_id: string | null;
  confidence: number;
  raw_command: string;
}
