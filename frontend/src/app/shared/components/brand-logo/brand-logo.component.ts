import { ChangeDetectionStrategy, Component } from '@angular/core';

import { BRAND_MARK_URL } from './brand-logo.constants';

@Component({
  selector: 'app-brand-logo',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    'aria-hidden': 'true',
    '[style.--brand-mark]': 'markUrl',
  },
  template: '',
  styles: [
    `
      :host {
        display: block;
        aspect-ratio: 1326 / 1389;
        background: linear-gradient(135deg, var(--color-text-primary) 35%, var(--color-accent) 100%);
        -webkit-mask: var(--brand-mark) center / contain no-repeat;
        mask: var(--brand-mark) center / contain no-repeat;
      }
    `,
  ],
})
export class BrandLogoComponent {
  protected readonly markUrl = `url('${BRAND_MARK_URL}')`;
}
