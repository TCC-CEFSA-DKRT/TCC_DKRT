import { ChangeDetectionStrategy, Component } from '@angular/core';

import { BrandLogoComponent } from '../brand-logo/brand-logo.component';
import { ThemeToggleComponent } from '../theme-toggle/theme-toggle.component';

@Component({
  selector: 'app-split-panel',
  standalone: true,
  imports: [BrandLogoComponent, ThemeToggleComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="split-panel">
      <div class="split-panel__brand">
        <div class="split-panel__brand-inner">
          <app-brand-logo class="split-panel__logo" />
          <h1 class="split-panel__brand-title">DKRT</h1>
          <p class="split-panel__brand-subtitle">Auditoria de Data Spaces</p>
          <p class="split-panel__brand-tagline">
            Opere o Orion Context Broker em linguagem natural.
          </p>
          <p class="split-panel__brand-note">NGSI-v2 e NGSI-LD · Smart Data Models</p>
        </div>
      </div>
      <div class="split-panel__form">
        <app-theme-toggle class="split-panel__theme" />
        <div class="split-panel__form-inner glass">
          <ng-content />
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .split-panel {
        display: flex;
        min-height: 100vh;
      }
      .split-panel__brand {
        position: relative;
        flex: 1 1 42%;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--space-8);
        overflow: hidden;
        background:
          radial-gradient(520px 420px at 30% 40%, rgba(var(--accent-rgb), 0.16), transparent 70%),
          linear-gradient(rgba(var(--accent-rgb), 0.06) 1px, transparent 1px) 0 0 / 32px 32px,
          linear-gradient(90deg, rgba(var(--accent-rgb), 0.06) 1px, transparent 1px) 0 0 / 32px 32px,
          var(--color-bg-raised);
        border-right: 1px solid var(--color-border-accent);
      }
      .split-panel__brand-inner {
        position: relative;
        max-width: 380px;
      }
      .split-panel__logo {
        width: 72px;
        margin-bottom: var(--space-6);
      }
      .split-panel__brand-title {
        font-size: 2.75rem;
        font-weight: 700;
        line-height: 1;
        letter-spacing: 0.04em;
        text-shadow: 0 0 26px rgba(var(--text-glow-rgb), 0.4);
      }
      .split-panel__brand-subtitle {
        margin: var(--space-2) 0 var(--space-4);
        color: var(--color-accent);
        font-family: var(--font-display);
        font-size: 1.0625rem;
        font-weight: 600;
      }
      .split-panel__brand-tagline {
        color: var(--color-text-secondary);
        font-size: 1rem;
        margin-bottom: var(--space-6);
      }
      .split-panel__brand-note {
        display: inline-block;
        padding: 4px 12px;
        border: 1px solid var(--color-border-accent);
        border-radius: 999px;
        color: var(--color-text-secondary);
        font-family: var(--font-mono);
        font-size: 0.75rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .split-panel__form {
        flex: 1 1 58%;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--space-8);
        position: relative;
      }
      .split-panel__theme {
        position: absolute;
        top: var(--space-6);
        right: var(--space-6);
      }
      .split-panel__form-inner {
        width: 100%;
        max-width: 420px;
        padding: var(--space-8);
      }
      @media (max-width: 768px) {
        .split-panel {
          flex-direction: column;
          min-height: auto;
        }
        .split-panel__brand {
          flex: none;
          padding: var(--space-6) var(--space-4);
          border-right: none;
          border-bottom: 1px solid var(--color-border-accent);
        }
        .split-panel__brand-inner {
          max-width: none;
        }
        .split-panel__brand-tagline {
          margin-bottom: var(--space-2);
        }
        .split-panel__form {
          flex: none;
          padding: var(--space-6) var(--space-4);
        }
        .split-panel__form-inner {
          padding: var(--space-6);
        }
      }
    `,
  ],
})
export class SplitPanelComponent {}
