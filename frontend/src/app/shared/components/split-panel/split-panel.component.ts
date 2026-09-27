import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-split-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="split-panel">
      <div class="split-panel__brand">
        <div class="split-panel__brand-inner">
          <h1 class="split-panel__brand-title">FIWARE Conformance Auditor</h1>
          <p class="split-panel__brand-tagline">
            Opere o Orion Context Broker em linguagem natural, sem aprender a API NGSI-v2.
          </p>
          <p class="split-panel__brand-note">NGSI-v2 · Smart Data Models</p>
        </div>
      </div>
      <div class="split-panel__form">
        <div class="split-panel__form-inner">
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
        flex: 1 1 40%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--color-accent);
        padding: var(--space-8);
      }
      .split-panel__brand-inner {
        max-width: 360px;
      }
      .split-panel__brand-title {
        color: #fff;
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: var(--space-4);
      }
      .split-panel__brand-tagline {
        color: #fff;
        font-size: 1rem;
        margin-bottom: var(--space-6);
      }
      .split-panel__brand-note {
        color: #fff;
        font-size: 0.75rem;
        font-weight: 500;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        opacity: 0.85;
      }
      .split-panel__form {
        flex: 1 1 60%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--color-surface);
        padding: var(--space-8);
      }
      .split-panel__form-inner {
        width: 100%;
        max-width: 360px;
      }
      @media (max-width: 768px) {
        .split-panel {
          flex-direction: column;
          min-height: auto;
        }
        .split-panel__brand {
          flex: none;
          padding: var(--space-6) var(--space-4);
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
      }
    `,
  ],
})
export class SplitPanelComponent {}
