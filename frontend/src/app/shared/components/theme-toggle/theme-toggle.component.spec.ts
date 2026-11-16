import { TestBed } from '@angular/core/testing';

import { THEME_ATTRIBUTE, THEME_STORAGE_KEY } from '../../../core/theme.constants';
import { ThemeToggleComponent } from './theme-toggle.component';

describe('ThemeToggleComponent', () => {
  beforeEach(() => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    TestBed.configureTestingModule({ imports: [ThemeToggleComponent] });
  });

  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY);
    document.documentElement.removeAttribute(THEME_ATTRIBUTE);
  });

  function render(): { button: HTMLButtonElement; detectChanges: () => void } {
    const fixture = TestBed.createComponent(ThemeToggleComponent);
    fixture.detectChanges();
    return {
      button: fixture.nativeElement.querySelector('button'),
      detectChanges: () => fixture.detectChanges(),
    };
  }

  it('offers the light theme while the dark theme is active', () => {
    const { button } = render();

    expect(button.textContent?.trim()).toBe('Tema claro');
    expect(button.getAttribute('aria-label')).toBe('Mudar para o tema claro');
  });

  it('switches to the light theme on click and then offers the dark theme back', () => {
    const { button, detectChanges } = render();

    button.click();
    detectChanges();

    expect(document.documentElement.getAttribute(THEME_ATTRIBUTE)).toBe('light');
    expect(button.textContent?.trim()).toBe('Tema escuro');
    expect(button.getAttribute('aria-label')).toBe('Mudar para o tema escuro');
  });
});
