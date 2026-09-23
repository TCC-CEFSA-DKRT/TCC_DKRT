import { TestBed } from '@angular/core/testing';
import { DiffViewComponent } from './diff-view.component';

describe('DiffViewComponent', () => {
  it('formats a structured proposed_patch object as readable JSON, never a bare [object Object]', () => {
    TestBed.configureTestingModule({ imports: [DiffViewComponent] });
    const fixture = TestBed.createComponent(DiffViewComponent);
    fixture.componentRef.setInput('currentValue', 'temp');
    fixture.componentRef.setInput('proposedValue', { from: 'temp', to: 'temperature' });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('temp');
    expect(text).toContain('"to": "temperature"');
    expect(text).not.toContain('[object Object]');
  });

  it('shows a placeholder, never a literal "null", for an absent value', () => {
    TestBed.configureTestingModule({ imports: [DiffViewComponent] });
    const fixture = TestBed.createComponent(DiffViewComponent);
    fixture.componentRef.setInput('currentValue', null);
    fixture.componentRef.setInput('proposedValue', 'temperature');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('(ausente)');
  });
});
