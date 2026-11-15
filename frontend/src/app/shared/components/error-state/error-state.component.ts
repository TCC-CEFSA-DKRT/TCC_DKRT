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
        gap: var(--space-3);
        padding: var(--space-8) var(--space-4);
        text-align: center;
        border: 1px solid color-mix(in srgb, var(--color-non-conformant) 45%, transparent);
        border-radius: var(--radius-lg);
        background: color-mix(in srgb, var(--color-non-conformant) 7%, transparent);
      }
      .error-state__message {
        margin: 0;
        color: var(--color-non-conformant);
        font-weight: 500;
      }
      .error-state__retry {
        border: 1px solid var(--color-border-strong);
        background: transparent;
        color: var(--color-text-primary);
        border-radius: var(--radius-md);
        padding: 6px 14px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
        transition: border-color 150ms ease-out, color 150ms ease-out;
      }
      .error-state__retry:hover {
        border-color: var(--color-accent);
        color: var(--color-accent);
      }
    `,
  ],
})
export class ErrorStateComponent {
  readonly message = input.required<string>();
  readonly retry = output<void>();
}
