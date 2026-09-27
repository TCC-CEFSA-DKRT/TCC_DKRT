import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/** Estado de erro obrigatório em toda tela (docs/design/design-system.md)
 * — mensagem explícita + "tentar novamente", nunca tela em branco ou
 * carregando infinito (fase8.spec.md, seções 3/4/5/6/7, cada uma com um
 * caso de teste "API indisponível -> erro explícito com retry"). */
@Component({
  selector: 'app-error-state',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="error-state" role="alert">
      <p class="error-state__message">{{ message() }}</p>
      <button type="button" class="error-state__retry" (click)="retry.emit()">
        Tentar novamente
      </button>
    </div>
  `,
  styles: [
    `
      .error-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: var(--space-3, 12px);
        padding: var(--space-8, 32px) var(--space-4, 16px);
        text-align: center;
      }
      .error-state__message {
        margin: 0;
        color: var(--color-non-conformant, #b23a3a);
        font-weight: 500;
      }
      .error-state__retry {
        border: 1px solid var(--color-border, #e2e5ea);
        background: var(--color-surface, #fff);
        color: var(--color-text-primary, #1a1d24);
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
        transition: border-color 150ms ease-out;
      }
      .error-state__retry:hover {
        border-color: var(--color-accent, #0f6e5c);
      }
    `,
  ],
})
export class ErrorStateComponent {
  readonly message = input.required<string>();
  readonly retry = output<void>();
}
