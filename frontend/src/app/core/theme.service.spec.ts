import { TestBed } from '@angular/core/testing';

import { THEME_ATTRIBUTE, THEME_STORAGE_KEY } from './theme.constants';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  let schemeListener: ((event: { matches: boolean }) => void) | null;

  function systemPrefersLight(matches: boolean): void {
    spyOn(window, 'matchMedia').and.returnValue({
      matches,
      addEventListener: (_type: string, listener: (event: { matches: boolean }) => void) => {
        schemeListener = listener;
      },
    } as unknown as MediaQueryList);
  }

  function currentAttribute(): string | null {
    return document.documentElement.getAttribute(THEME_ATTRIBUTE);
  }

  beforeEach(() => {
    schemeListener = null;
    localStorage.removeItem(THEME_STORAGE_KEY);
    TestBed.configureTestingModule({});
  });

  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY);
    document.documentElement.removeAttribute(THEME_ATTRIBUTE);
  });

  it('follows the operating system when the user never chose a theme', () => {
    systemPrefersLight(true);

    const service = TestBed.inject(ThemeService);

    expect(service.theme()).toBe('light');
    expect(currentAttribute()).toBe('light');
  });

  it('uses the dark theme when the operating system does not prefer light', () => {
    systemPrefersLight(false);

    const service = TestBed.inject(ThemeService);

    expect(service.theme()).toBe('dark');
    expect(currentAttribute()).toBe('dark');
  });

  it('keeps the theme the user chose before, even if the system prefers the other one', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    systemPrefersLight(true);

    const service = TestBed.inject(ThemeService);

    expect(service.theme()).toBe('dark');
  });

  it('ignores an unknown value saved in the browser and falls back to the system theme', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'purple');
    systemPrefersLight(true);

    const service = TestBed.inject(ThemeService);

    expect(service.theme()).toBe('light');
  });

  it('switches the theme on the page and remembers the choice for the next visit', () => {
    systemPrefersLight(false);
    const service = TestBed.inject(ThemeService);

    service.toggle();
    TestBed.tick();

    expect(service.theme()).toBe('light');
    expect(currentAttribute()).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('changes along with the system while the user has not chosen a theme', () => {
    systemPrefersLight(false);
    const service = TestBed.inject(ThemeService);

    schemeListener?.({ matches: true });
    TestBed.tick();

    expect(service.theme()).toBe('light');
    expect(currentAttribute()).toBe('light');
  });

  it('stops following the system once the user chooses a theme', () => {
    systemPrefersLight(false);
    const service = TestBed.inject(ThemeService);
    service.toggle();

    schemeListener?.({ matches: false });
    TestBed.tick();

    expect(service.theme()).toBe('light');
  });

  it('still switches the theme when the browser blocks saving the choice', () => {
    systemPrefersLight(false);
    spyOn(Storage.prototype, 'getItem').and.throwError('blocked');
    spyOn(Storage.prototype, 'setItem').and.throwError('blocked');
    const service = TestBed.inject(ThemeService);

    service.toggle();
    TestBed.tick();

    expect(service.theme()).toBe('light');
    expect(currentAttribute()).toBe('light');
  });
});
