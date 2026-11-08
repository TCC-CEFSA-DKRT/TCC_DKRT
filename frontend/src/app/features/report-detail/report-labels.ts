import {
  ConformanceStatus,
  RecommendationAction,
  ViolationSeverity,
} from '../../shared/models/audit.models';

/** Issue #22 — textos em português usados pelo relatório. Ficam fora do
 * componente para que os testes e outras telas possam reaproveitá-los. */

export const SEVERITY_ORDER: readonly ViolationSeverity[] = ['error', 'warning', 'info'];

export const SEVERITY_GROUP_TITLES: Record<ViolationSeverity, string> = {
  error: 'Erros',
  warning: 'Avisos',
  info: 'Informações',
};

/** Regras do Nível 1 (`structural_validator.py` e `run_audit.py`). As regras
 * do Nível 2 são texto livre do SLM e caem no fallback de `ruleLabel()`. */
const RULE_LABELS: Record<string, string> = {
  required_property_missing: 'Atributo obrigatório ausente',
  type_mismatch: 'Tipo de dado incorreto',
  format_invalid: 'Formato inválido',
  value_out_of_range: 'Valor fora do intervalo permitido',
  enum_violation: 'Valor fora da lista permitida',
  unexpected_property: 'Atributo não previsto no modelo',
  malformed_attribute: 'Atributo fora do formato NGSI-v2',
  // Nível 2 — nome usado com frequência pelo SLM (ver dataset/).
  attribute_name_synonym: 'Nome de atributo diferente do definido no modelo',
};

export function ruleLabel(rule: string): string {
  const known = RULE_LABELS[rule];
  if (known) {
    return known;
  }
  const readable = rule.replace(/[_-]+/g, ' ').trim();
  return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : rule;
}

export const ACTION_LABELS: Record<RecommendationAction, string> = {
  rename_attribute: 'Renomear o atributo',
  add_missing_attribute: 'Adicionar o atributo ausente',
  fix_type: 'Corrigir o tipo de dado',
  fix_format: 'Corrigir o formato',
};

/** Filtros por status da entidade. "Sem modelo" corresponde a
 * `no_model_found`; `schema_unavailable` só aparece quando existir. */
export type StatusFilter = 'all' | ConformanceStatus;

export const STATUS_FILTER_LABELS: Record<StatusFilter, string> = {
  all: 'Todas',
  conformant: 'Conforme',
  partial: 'Parcial',
  non_conformant: 'Não conforme',
  no_model_found: 'Sem modelo',
  schema_unavailable: 'Schema indisponível',
};
