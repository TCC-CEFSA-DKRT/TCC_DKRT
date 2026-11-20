import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { BADGE_STYLES } from './status-badge.constants';
import { BadgeKind, BadgeStyle } from './status-badge.interface';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="badge" [style.--badge-color]="'var(' + style().colorVar + ')'">
      {{ style().label }}
    </span>
  `,
  styles: [
    `
      .badge {
        display: inline-flex;
        align-items: center;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        line-height: 1.5;
        color: var(--badge-color);
        background-color: color-mix(in srgb, var(--badge-color) 14%, transparent);
        border: 1px solid color-mix(in srgb, var(--badge-color) 55%, transparent);
        white-space: nowrap;
      }
    `,
  ],
})
export class StatusBadgeComponent {
  readonly status = input.required<BadgeKind>();

  protected readonly style = computed<BadgeStyle>(() => BADGE_STYLES[this.status()]);
}
