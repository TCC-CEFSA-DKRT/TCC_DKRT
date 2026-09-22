import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Skeleton do layout real da tela (docs/design/design-system.md) — nunca
 * um spinner genérico centralizado sem contexto do que está carregando.
 * `rows` controla quantas linhas de skeleton desenhar (uma tabela de
 * Audit Runs desenha ~5 linhas, um card de resumo desenha 1-2). */
@Component({
  selector: 'app-loading-skeleton',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @for (row of rowsArray(); track $index) {
      <div class="skeleton-row"></div>
    }
  `,
  styles: [
    `
      .skeleton-row {
        height: 20px;
        border-radius: 4px;
        margin-bottom: var(--space-2, 8px);
        background: linear-gradient(
          90deg,
          var(--color-border, #e2e5ea) 25%,
          #edeff2 37%,
          var(--color-border, #e2e5ea) 63%
        );
        background-size: 400% 100%;
        animation: skeleton-loading 1.4s ease infinite;
      }
      @keyframes skeleton-loading {
        0% {
          background-position: 100% 50%;
        }
        100% {
          background-position: 0 50%;
        }
      }
    `,
  ],
})
export class LoadingSkeletonComponent {
  readonly rows = input<number>(4);

  protected rowsArray(): number[] {
    return Array.from({ length: this.rows() });
  }
}
