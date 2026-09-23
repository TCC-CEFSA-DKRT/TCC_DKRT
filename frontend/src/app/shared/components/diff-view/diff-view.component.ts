import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Diff visual "encontrado" vs. "esperado" (violações) ou "atual" vs.
 * `proposed_patch` (recomendações) — fase8.spec.md, seção 5: "o diff
 * visual mostra claramente o valor atual vs. o proposed_patch — nunca só
 * o rationale em texto sem o dado estruturado ao lado." Aceita qualquer
 * valor (string das violações, ou objeto estruturado do patch) e formata
 * cada lado de forma legível. */
@Component({
  selector: 'app-diff-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="diff-view">
      <div class="diff-view__side diff-view__side--current">
        <span class="diff-view__label">{{ currentLabel() }}</span>
        <code class="diff-view__value diff-view__value--current">{{ currentText() }}</code>
      </div>
      <div class="diff-view__side diff-view__side--proposed">
        <span class="diff-view__label">{{ proposedLabel() }}</span>
        <code class="diff-view__value diff-view__value--proposed">{{ proposedText() }}</code>
      </div>
    </div>
  `,
  styles: [
    `
      .diff-view {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: var(--space-3, 12px);
      }
      .diff-view__side {
        display: flex;
        flex-direction: column;
        gap: var(--space-1, 4px);
        padding: var(--space-2, 8px) var(--space-3, 12px);
        border-radius: 6px;
        border: 1px solid var(--color-border, #e2e5ea);
      }
      .diff-view__label {
        font-size: 0.75rem;
        font-weight: 500;
        color: var(--color-text-secondary, #5b6270);
      }
      .diff-view__value {
        font-family: ui-monospace, 'SF Mono', Menlo, monospace;
        font-size: 0.875rem;
        word-break: break-all;
        white-space: pre-wrap;
      }
      .diff-view__value--current {
        color: var(--color-non-conformant, #b23a3a);
      }
      .diff-view__value--proposed {
        color: var(--color-conformant, #1a7f4b);
      }
    `,
  ],
})
export class DiffViewComponent {
  readonly currentLabel = input<string>('Encontrado');
  readonly proposedLabel = input<string>('Esperado');
  readonly currentValue = input<unknown>(null);
  readonly proposedValue = input<unknown>(null);

  protected readonly currentText = computed(() => this.format(this.currentValue()));
  protected readonly proposedText = computed(() => this.format(this.proposedValue()));

  private format(value: unknown): string {
    if (value === null || value === undefined) {
      return '(ausente)';
    }
    if (typeof value === 'string') {
      return value;
    }
    return JSON.stringify(value, null, 2);
  }
}
