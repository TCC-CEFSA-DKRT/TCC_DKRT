import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';

import { LOGIN_PATH } from '../../../core/session.constants';
import { SessionService } from '../../../core/session.service';

@Component({
  selector: 'app-user-menu',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="user-menu">
      <span class="user-menu__avatar" aria-hidden="true">{{ initial() }}</span>
      <span class="user-menu__identity">
        @if (email(); as email) {
          <span class="user-menu__email">{{ email }}</span>
        }
        <span class="user-menu__tenant">{{ tenant() }}</span>
      </span>
      <button type="button" class="user-menu__logout" (click)="onLogout()">
        <svg class="user-menu__icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" />
          <path d="M10 16l-4-4 4-4M6 12h10" />
        </svg>
        Sair
      </button>
    </div>
  `,
  styles: [
    `
      .user-menu {
        display: flex;
        align-items: center;
        gap: var(--space-3);
      }
      .user-menu__avatar {
        display: grid;
        place-items: center;
        width: 34px;
        height: 34px;
        border-radius: 50%;
        background: var(--gradient-accent);
        color: var(--color-on-accent);
        font-family: var(--font-display);
        font-weight: 700;
        text-transform: uppercase;
      }
      .user-menu__identity {
        display: flex;
        flex-direction: column;
        line-height: 1.25;
        text-align: right;
      }
      .user-menu__email {
        font-size: 0.875rem;
        font-weight: 600;
        color: var(--color-text-primary);
      }
      .user-menu__tenant {
        font-family: var(--font-mono);
        font-size: 0.75rem;
        color: var(--color-text-secondary);
      }
      .user-menu__logout {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        font-size: 0.8125rem;
        font-weight: 500;
        color: var(--color-text-secondary);
        background: transparent;
        border: 1px solid var(--color-border-strong);
        border-radius: var(--radius-md);
        cursor: pointer;
        transition: color 150ms ease-out, border-color 150ms ease-out;
      }
      .user-menu__logout:hover {
        color: var(--color-accent);
        border-color: var(--color-accent);
      }
      .user-menu__icon {
        width: 16px;
        height: 16px;
        fill: none;
        stroke: currentColor;
        stroke-width: 1.8;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
    `,
  ],
})
export class UserMenuComponent {
  private readonly sessionService = inject(SessionService);
  private readonly router = inject(Router);

  protected readonly email = computed(() => this.sessionService.session()?.login_email ?? null);
  protected readonly tenant = computed(() => this.sessionService.session()?.tenant?.fiware_service ?? '');
  protected readonly initial = computed(() => (this.email() ?? this.tenant()).charAt(0));

  protected onLogout(): void {
    this.sessionService.logout().subscribe(() => this.router.navigateByUrl(LOGIN_PATH));
  }
}
