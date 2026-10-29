import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { SplitPanelComponent } from './split-panel.component';

@Component({
  standalone: true,
  imports: [SplitPanelComponent],
  template: `<app-split-panel><button class="probe">conteúdo do formulário</button></app-split-panel>`,
})
class HostComponent {}

describe('SplitPanelComponent', () => {
  it('renders the brand copy and projects the consumer content into the form panel', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;

    expect(el.querySelector('.split-panel__brand-title')?.textContent).toContain('DKRT');
    expect(el.querySelector('.split-panel__brand-subtitle')?.textContent).toContain(
      'Auditoria de Data Spaces'
    );
    const projected = el.querySelector('.split-panel__form .probe');
    expect(projected?.textContent).toContain('conteúdo do formulário');
  });
});
