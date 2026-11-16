import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { SessionService } from '../../core/session.service';
import { ThemeToggleComponent } from '../../shared/components/theme-toggle/theme-toggle.component';
import { UserMenuComponent } from '../../shared/components/user-menu/user-menu.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ThemeToggleComponent, UserMenuComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="shell">
      <nav class="shell__nav" aria-label="Menu principal">
        <div class="shell__nav-inner">
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
          <app-theme-toggle />
          <span class="shell__project">TCC · FESA</span>
        </div>
        </div>
      </nav>
      <main class="shell__content">
        @if (session()?.deployment_mode === 'saas' && session()?.tenant) {
          <header class="shell__topbar">
            <app-user-menu />
          </header>
        }
        <router-outlet />
      </main>
    </div>
  `,
  styles: [
    `
      .shell {
        display: flex;
        min-height: 100vh;
      }
      .shell__nav {
        width: 250px;
        flex-shrink: 0;
        background: var(--gradient-nav);
        border-right: 1px solid var(--color-border-accent);
      }
      .shell__nav-inner {
        position: sticky;
        top: 0;
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
        height: 100vh;
        padding: var(--space-6) var(--space-4);
      }
      .shell__brand {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: 0 var(--space-2) var(--space-6);
      }
      .shell__logo {
        display: grid;
        place-items: center;
        width: 46px;
        height: 46px;
        flex-shrink: 0;
        border-radius: 12px;
        background: var(--gradient-accent);
        color: var(--color-on-accent);
        font-family: var(--font-display);
        font-weight: 700;
        font-size: 1.0625rem;
        box-shadow: var(--glow-accent);
      }
      .shell__brand-text {
        display: flex;
        flex-direction: column;
        line-height: 1.2;
      }
      .shell__brand-name {
        font-family: var(--font-display);
        font-weight: 700;
        font-size: 1.375rem;
        letter-spacing: 0.04em;
      }
      .shell__brand-subtitle {
        margin-top: 2px;
        font-size: 0.71875rem;
        white-space: nowrap;
        color: var(--color-text-muted);
      }
      .shell__link {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        min-height: 46px;
        padding: 0 var(--space-3);
        border-radius: var(--radius-md);
        color: var(--color-text-secondary);
        text-decoration: none;
        font-size: 0.96875rem;
        transition: background-color 150ms ease-out, color 150ms ease-out;
      }
      .shell__icon {
        width: 20px;
        height: 20px;
        flex-shrink: 0;
        fill: none;
        stroke: currentColor;
        stroke-width: 1.6;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
      .shell__link:hover {
        background: rgba(var(--accent-rgb), 0.06);
        color: var(--color-text-primary);
      }
      .shell__link--active {
        background: linear-gradient(90deg, rgba(var(--accent-rgb), 0.18), rgba(var(--accent-rgb), 0.03));
        box-shadow: inset 3px 0 0 var(--color-accent), 0 0 22px rgba(var(--accent-rgb), 0.12);
        color: var(--color-nav-active-text);
      }
      .shell__content {
        flex: 1;
        min-width: 0;
        padding: var(--space-8) var(--space-8) var(--space-8) 48px;
      }
      .shell__footer {
        margin-top: auto;
        padding: var(--space-4) var(--space-2) 0;
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
      }
      .shell__topbar {
        display: flex;
        justify-content: flex-end;
        margin: calc(-1 * var(--space-4)) 0 var(--space-4);
      }
      .shell__project {
        font-size: 0.75rem;
        letter-spacing: 0.04em;
        color: var(--color-text-muted);
      }
    `,
  ],
})
export class ShellComponent {
  private readonly sessionService = inject(SessionService);

  protected readonly session = this.sessionService.session;
}
