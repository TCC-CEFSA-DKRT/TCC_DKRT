import { TestBed } from '@angular/core/testing';

import { BrandLogoComponent } from './brand-logo.component';

describe('BrandLogoComponent', () => {
  function render() {
    TestBed.configureTestingModule({ imports: [BrandLogoComponent] });
    const fixture = TestBed.createComponent(BrandLogoComponent);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('draws the team mark from the SVG served with the app', () => {
    const host = render();

    expect(host.style.getPropertyValue('--brand-mark')).toContain('/brand/dkrt-mark.svg');
  });

  it('is hidden from screen readers, because the name DKRT is written next to it', () => {
    const host = render();

    expect(host.getAttribute('aria-hidden')).toBe('true');
    expect(host.textContent?.trim()).toBe('');
  });
});
