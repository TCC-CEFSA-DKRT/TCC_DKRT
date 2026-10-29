import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { SessionService } from '../../core/session.service';

/** Casca de navegação — as cinco telas (fase8.spec.md, seções 3-7) vivem
 * atrás do `<router-outlet>`, carregadas lazy por feature (seção 1).
 * Issue #21: menu em português, identidade DKRT e ícones (SVG inline,
 * `currentColor`, sem dependência externa). */
@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="shell">
      <nav class="shell__nav" aria-label="Menu principal">
        <div class="shell__brand">
          <span class="shell__logo" aria-hidden="true">DK</span>
          <span class="shell__brand-text">
            <span class="shell__brand-name">DKRT</span>
            <span class="shell__brand-subtitle">Auditoria de Data Spaces</span>
          </span>
        </div>

        <a routerLink="/dashboard" routerLinkActive="shell__link--active" class="shell__link">
          <svg class="shell__icon" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="3" y="3" width="7" height="9" rx="1.5" />
            <rect x="14" y="3" width="7" height="5" rx="1.5" />
            <rect x="14" y="12" width="7" height="9" rx="1.5" />
            <rect x="3" y="16" width="7" height="5" rx="1.5" />
          </svg>
          Painel
        </a>
        <a routerLink="/audit-runs" routerLinkActive="shell__link--active" class="shell__link">
          <svg class="shell__icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 6h11M9 12h11M9 18h11" />
            <path d="M3.5 6l1.2 1.2L7 5M3.5 12l1.2 1.2L7 11M3.5 18l1.2 1.2L7 17" />
          </svg>
          Auditorias
        </a>
        <a
          routerLink="/natural-language"
          routerLinkActive="shell__link--active"
          class="shell__link"
        >
          <svg class="shell__icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 5h16v11H10l-4 4v-4H4z" />
            <path d="M8 9.5h8M8 12.5h5" />
          </svg>
          Assistente
        </a>
        <a routerLink="/catalog" routerLinkActive="shell__link--active" class="shell__link">
          <svg class="shell__icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" />
            <path d="M5 17a3 3 0 0 1 3-3h11" />
          </svg>
          Catálogo
        </a>
        @if (session()?.deployment_mode === 'selfhosted') {
          <a routerLink="/config" routerLinkActive="shell__link--active" class="shell__link">
            <svg class="shell__icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
              <circle cx="16" cy="7" r="2" />
              <circle cx="10" cy="17" r="2" />
            </svg>
            Configuração
          </a>
        }
        <div class="shell__footer">
          @if (session()?.deployment_mode === 'saas') {
            <span class="shell__tenant">{{ session()?.tenant?.fiware_service }}</span>
            <button type="button" class="shell__logout" (click)="onLogout()">Sair</button>
          }
          <span class="shell__project">TCC · FESA</span>
        </div>
      </nav>
      <main class="shell__content">
        <router-outlet />
      </main>
    </div>
  `,
  styles: [
    `
      .shell {
        display: flex;
        min-height: 100vh;
        background: var(--color-bg);
      }
      .shell__nav {
        display: flex;
        flex-direction: column;
        gap: var(--space-1, 4px);
        width: 240px;
        flex-shrink: 0;
        padding: var(--space-4, 16px);
        background: var(--color-surface);
        border-right: 1px solid var(--color-border);
      }
      .shell__brand {
        display: flex;
        align-items: center;
        gap: var(--space-3, 12px);
        padding: var(--space-1, 4px) var(--space-1, 4px) var(--space-4, 16px);
        margin-bottom: var(--space-3, 12px);
        border-bottom: 1px solid var(--color-border);
      }
      .shell__logo {
        display: grid;
        place-items: center;
        width: 36px;
        height: 36px;
        flex-shrink: 0;
        border-radius: 8px;
        background: var(--color-accent);
        color: #fff;
        font-weight: 700;
        font-size: 0.875rem;
        letter-spacing: 0.02em;
      }
      .shell__brand-text {
        display: flex;
        flex-direction: column;
        line-height: 1.2;
      }
      .shell__brand-name {
        font-weight: 700;
        font-size: 1.125rem;
        color: var(--color-text-primary);
      }
      .shell__brand-subtitle {
        font-size: 0.6875rem;
        white-space: nowrap;
        color: var(--color-text-secondary);
      }
      .shell__link {
        display: flex;
        align-items: center;
        gap: var(--space-3, 12px);
        padding: var(--space-2, 8px) var(--space-3, 12px);
        border-radius: 6px;
        color: var(--color-text-secondary);
        text-decoration: none;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background-color 150ms ease-out, color 150ms ease-out;
      }
      .shell__icon {
        width: 18px;
        height: 18px;
        flex-shrink: 0;
        fill: none;
        stroke: currentColor;
        stroke-width: 1.75;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
      .shell__link:hover {
        background: var(--color-bg);
        color: var(--color-text-primary);
      }
      .shell__link--active {
        background: color-mix(in srgb, var(--color-accent) 10%, transparent);
        color: var(--color-accent);
        font-weight: 600;
      }
      .shell__content {
        flex: 1;
        min-width: 0;
        padding: var(--space-6, 24px) var(--space-8, 32px);
      }
      .shell__footer {
        margin-top: auto;
        padding-top: var(--space-4, 16px);
        border-top: 1px solid var(--color-border);
        display: flex;
        flex-direction: column;
        gap: var(--space-2, 8px);
      }
      .shell__tenant {
        padding: 0 var(--space-3, 12px);
        font-size: 0.75rem;
        font-weight: 500;
        color: var(--color-text-secondary);
      }
      .shell__project {
        padding: 0 var(--space-3, 12px);
        font-size: 0.75rem;
        color: var(--color-text-secondary);
      }
      .shell__logout {
        border: none;
        background: none;
        text-align: left;
        padding: var(--space-2, 8px) var(--space-3, 12px);
        border-radius: 6px;
        color: var(--color-text-secondary);
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
      }
      .shell__logout:hover {
        background: var(--color-bg);
        color: var(--color-text-primary);
      }
    `,
  ],
})
export class ShellComponent {
  private readonly sessionService = inject(SessionService);
  private readonly router = inject(Router);

  protected readonly session = this.sessionService.session;

  protected onLogout(): void {
    this.sessionService.logout().subscribe(() => this.router.navigateByUrl('/login'));
  }
}
