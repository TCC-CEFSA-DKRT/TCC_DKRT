import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { ThemeService } from '../../../core/theme.service';
import { THEME_TOGGLE_LABEL, THEME_TOGGLE_TEXT } from './theme-toggle.constants';

@Component({
  selector: 'app-theme-toggle',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      type="button"
      class="theme-toggle"
      [attr.aria-label]="label()"
      [title]="label()"
      (click)="themeService.toggle()"
    >
      <svg class="theme-toggle__icon" viewBox="0 0 24 24" aria-hidden="true">
        @if (themeService.theme() === 'dark') {
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" />
        } @else {
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
        }
      </svg>
      <span class="theme-toggle__text">{{ text() }}</span>
    </button>
  `,
  styles: [
    `
      .theme-toggle {
        display: inline-flex;
        align-items: center;
        gap: var(--space-2);
        padding: 6px 12px;
        font-size: 0.8125rem;
        color: var(--color-text-secondary);
        background: transparent;
        border: 1px solid var(--color-border-strong);
        border-radius: var(--radius-md);
        cursor: pointer;
        transition: color 150ms ease-out, border-color 150ms ease-out;
      }
      .theme-toggle:hover {
        color: var(--color-accent);
        border-color: var(--color-accent);
      }
      .theme-toggle__icon {
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
export class ThemeToggleComponent {
  protected readonly themeService = inject(ThemeService);
  protected readonly text = computed(() => THEME_TOGGLE_TEXT[this.themeService.theme()]);
  protected readonly label = computed(() => THEME_TOGGLE_LABEL[this.themeService.theme()]);
}
