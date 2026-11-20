import { BadgeKind, BadgeStyle } from './status-badge.interface';

export const BADGE_STYLES: Record<BadgeKind, BadgeStyle> = {
  conformant: { label: 'Conforme', colorVar: '--color-conformant' },
  partial: { label: 'Parcial', colorVar: '--color-partial' },
  non_conformant: { label: 'Não conforme', colorVar: '--color-non-conformant' },
  no_model_found: { label: 'Modelo não encontrado', colorVar: '--color-no-model' },
  schema_unavailable: { label: 'Schema indisponível', colorVar: '--color-schema-unavailable' },
  queued: { label: 'Na fila', colorVar: '--color-no-model' },
  running: { label: 'Em execução', colorVar: '--color-accent' },
  completed: { label: 'Concluído', colorVar: '--color-conformant' },
  failed: { label: 'Falhou', colorVar: '--color-non-conformant' },
  no_entities_found: { label: 'Nenhuma entidade encontrada', colorVar: '--color-warning' },
  error: { label: 'Erro', colorVar: '--color-non-conformant' },
  warning: { label: 'Aviso', colorVar: '--color-warning' },
  info: { label: 'Info', colorVar: '--color-info' },
};
