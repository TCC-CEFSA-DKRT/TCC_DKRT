import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Estado vazio obrigatório em toda tela (docs/design/design-system.md,
 * "Estados obrigatórios por tela") — nunca uma tabela/gráfico em branco
 * sem explicação. `actionLabel`/`actionRoute` são opcionais: nem todo
 * vazio tem uma ação óbvia (ex.: Catalog nunca sincronizado ainda tem
 * ação "sincronizar" fora desta fase — administrativo, seção 7). */
@Component({
  selector: 'app-empty-state',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="empty-state">
      <p class="empty-state__message">{{ message() }}</p>
      @if (hint()) {
        <p class="empty-state__hint">{{ hint() }}</p>
      }
    </div>
  `,
  styles: [
    `
      .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: var(--space-2);
        padding: var(--space-8) var(--space-4);
        text-align: center;
        color: var(--color-text-secondary);
        border: 1px dashed var(--color-border-accent);
        border-radius: var(--radius-lg);
        background: rgba(14, 25, 36, 0.5);
      }
      .empty-state__message {
        font-size: 1rem;
        font-weight: 500;
        color: var(--color-text-primary);
        margin: 0;
      }
      .empty-state__hint {
        font-size: 0.875rem;
        margin: 0;
        max-width: 480px;
      }
    `,
  ],
})
export class EmptyStateComponent {
  readonly message = input.required<string>();
  readonly hint = input<string | null>(null);
}
