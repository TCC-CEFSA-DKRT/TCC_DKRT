/** Espelha `InterpretAuditRequest`/`InterpretAuditResponse` (backend). */
export interface InterpretAuditRequest {
  command_text: string;
}

/** Issue #21 — `clarify` (pedido ambíguo, com pergunta de esclarecimento)
 * e `out_of_scope` (pedido fora do domínio FIWARE, nada é executado). */
export type CommandIntent = 'audit' | 'discovery' | 'clarify' | 'out_of_scope';

/** Mesmo limite de `COMMAND_TEXT_MAX_LENGTH` no backend (schemas.py). */
export const COMMAND_TEXT_MAX_LENGTH = 500;

export interface InterpretAuditResponse {
  intent: CommandIntent;
  entity_type: string | null;
  entity_id: string | null;
  confidence: number;
  raw_command: string;
  discovered_types: string[] | null;
  broker_reachable: boolean | null;
  /** Preenchido quando `intent === 'clarify'`. Opcional para tolerar um
   * backend anterior à issue #21. */
  clarification_question?: string | null;
  /** `false` quando o modelo de linguagem (Ollama) não respondeu. Ausente
   * equivale a `true`. */
  interpreter_available?: boolean;
}
