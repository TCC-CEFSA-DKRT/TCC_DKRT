import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** União de todos os vocabulários de status/severidade que este badge sabe
 * mapear — `ConformanceStatus`, `RunStatus` e `ViolationSeverity` (ver
 * shared/models/audit.models.ts) compartilham o mesmo componente porque
 * usam exatamente os mesmos tokens de cor (docs/design/design-system.md). */
export type BadgeKind =
  | 'conformant'
  | 'partial'
  | 'non_conformant'
  | 'no_model_found'
  | 'schema_unavailable'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'error'
  | 'warning'
  | 'info';

interface BadgeStyle {
  label: string;
  colorVar: string;
}

const BADGE_STYLES: Record<BadgeKind, BadgeStyle> = {
  conformant: { label: 'Conforme', colorVar: '--color-conformant' },
  partial: { label: 'Parcial', colorVar: '--color-partial' },
  non_conformant: { label: 'Não conforme', colorVar: '--color-non-conformant' },
  no_model_found: { label: 'Modelo não encontrado', colorVar: '--color-no-model' },
  schema_unavailable: { label: 'Schema indisponível', colorVar: '--color-schema-unavailable' },
  queued: { label: 'Na fila', colorVar: '--color-no-model' },
  running: { label: 'Em execução', colorVar: '--color-accent' },
  completed: { label: 'Concluído', colorVar: '--color-conformant' },
  failed: { label: 'Falhou', colorVar: '--color-non-conformant' },
  error: { label: 'Erro', colorVar: '--color-non-conformant' },
  warning: { label: 'Aviso', colorVar: '--color-warning' },
  info: { label: 'Info', colorVar: '--color-info' },
};

@Component({
  selector: 'app-status-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="badge" [style.--badge-color]="'var(' + style().colorVar + ')'">
      {{ style().label }}
    </span>
  `,
  styles: [
    `
      .badge {
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        line-height: 1.4;
        color: var(--badge-color);
        background-color: color-mix(in srgb, var(--badge-color) 12%, transparent);
        white-space: nowrap;
      }
    `,
  ],
})
export class StatusBadgeComponent {
  readonly status = input.required<BadgeKind>();

  protected readonly style = computed<BadgeStyle>(() => BADGE_STYLES[this.status()]);
}
