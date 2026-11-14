import { RecommendationAction, ViolationSeverity } from '../../shared/models/audit.models';
import { StatusFilter } from './report-detail.models';

export const SEVERITY_ORDER: readonly ViolationSeverity[] = ['error', 'warning', 'info'];

export const SEVERITY_GROUP_TITLES: Record<ViolationSeverity, string> = {
  error: 'Erros',
  warning: 'Avisos',
  info: 'Informações',
};

export const RULE_LABELS: Readonly<Record<string, string>> = {
  required_property_missing: 'Atributo obrigatório ausente',
  type_mismatch: 'Tipo de dado incorreto',
  format_invalid: 'Formato inválido',
  value_out_of_range: 'Valor fora do intervalo permitido',
  enum_violation: 'Valor fora da lista permitida',
  unexpected_property: 'Atributo não previsto no modelo',
  malformed_attribute: 'Atributo fora do formato NGSI-v2',
  attribute_name_synonym: 'Nome de atributo diferente do definido no modelo',
};

export const ACTION_LABELS: Record<RecommendationAction, string> = {
  rename_attribute: 'Renomear o atributo',
  add_missing_attribute: 'Adicionar o atributo ausente',
  fix_type: 'Corrigir o tipo de dado',
  fix_format: 'Corrigir o formato',
};

export const STATUS_FILTER_LABELS: Record<StatusFilter, string> = {
  all: 'Todas',
  conformant: 'Conforme',
  partial: 'Parcial',
  non_conformant: 'Não conforme',
  no_model_found: 'Sem modelo',
  schema_unavailable: 'Schema indisponível',
};

export const ALWAYS_VISIBLE_FILTERS: readonly StatusFilter[] = [
  'all',
  'conformant',
  'partial',
  'non_conformant',
  'no_model_found',
];
