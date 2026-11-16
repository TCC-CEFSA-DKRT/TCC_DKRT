import { DOCUMENT } from '@angular/common';
import { Injectable, computed, effect, inject, signal } from '@angular/core';

import { LIGHT_SCHEME_QUERY, THEME_ATTRIBUTE, THEME_STORAGE_KEY } from './theme.constants';
import { Theme } from './theme.interface';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly lightScheme = this.document.defaultView?.matchMedia?.(LIGHT_SCHEME_QUERY) ?? null;
  private readonly chosenTheme = signal<Theme | null>(this.readChosenTheme());
  private readonly systemTheme = signal<Theme>(this.lightScheme?.matches ? 'light' : 'dark');

  readonly theme = computed<Theme>(() => this.chosenTheme() ?? this.systemTheme());

  constructor() {
    this.lightScheme?.addEventListener?.('change', (event) =>
      this.systemTheme.set(event.matches ? 'light' : 'dark')
    );
    this.applyTheme(this.theme());
    effect(() => this.applyTheme(this.theme()));
  }

  toggle(): void {
    const next: Theme = this.theme() === 'dark' ? 'light' : 'dark';
    this.chosenTheme.set(next);
    try {
      this.document.defaultView?.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      return;
    }
  }

  private applyTheme(theme: Theme): void {
    this.document.documentElement.setAttribute(THEME_ATTRIBUTE, theme);
  }

  private readChosenTheme(): Theme | null {
    try {
      const stored = this.document.defaultView?.localStorage.getItem(THEME_STORAGE_KEY);
      return stored === 'dark' || stored === 'light' ? stored : null;
    } catch {
      return null;
    }
  }
}
