import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { SessionService } from '../../core/session.service';

/** Casca de navegação — as cinco telas (fase8.spec.md, seções 3-7) vivem
 * atrás do `<router-outlet>`, carregadas lazy por feature (seção 1). */
@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="shell">
      <nav class="shell__nav">
        <span class="shell__brand">FIWARE Auditor</span>
        <a routerLink="/dashboard" routerLinkActive="shell__link--active" class="shell__link">
          Dashboard
        </a>
        <a routerLink="/audit-runs" routerLinkActive="shell__link--active" class="shell__link">
          Audit Runs
        </a>
        <a
          routerLink="/natural-language"
          routerLinkActive="shell__link--active"
          class="shell__link"
        >
          Natural Language
        </a>
        <a routerLink="/catalog" routerLinkActive="shell__link--active" class="shell__link">
          Catalog
        </a>
        @if (session()?.deployment_mode === 'selfhosted') {
          <a routerLink="/config" routerLinkActive="shell__link--active" class="shell__link">
            Configuração
          </a>
        }
        <div class="shell__footer">
          @if (session()?.deployment_mode === 'saas') {
            <span class="shell__tenant">{{ session()?.tenant?.fiware_service }}</span>
            <button type="button" class="shell__logout" (click)="onLogout()">Sair</button>
          }
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
        width: 220px;
        flex-shrink: 0;
        padding: var(--space-4, 16px);
        background: var(--color-surface);
        border-right: 1px solid var(--color-border);
      }
      .shell__brand {
        font-weight: 700;
        font-size: 1.125rem;
        color: var(--color-text-primary);
        margin-bottom: var(--space-4, 16px);
      }
      .shell__link {
        padding: var(--space-2, 8px) var(--space-3, 12px);
        border-radius: 6px;
        color: var(--color-text-secondary);
        text-decoration: none;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background-color 150ms ease-out, color 150ms ease-out;
      }
      .shell__link:hover {
        background: var(--color-bg);
        color: var(--color-text-primary);
      }
      .shell__link--active {
        background: color-mix(in srgb, var(--color-accent) 10%, transparent);
        color: var(--color-accent);
      }
      .shell__content {
        flex: 1;
        min-width: 0;
        padding: var(--space-6, 24px);
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
