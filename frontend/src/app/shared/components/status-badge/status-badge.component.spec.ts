import { TestBed } from '@angular/core/testing';
import { StatusBadgeComponent } from './status-badge.component';

describe('StatusBadgeComponent', () => {
  it('renders the Portuguese label for a given status', () => {
    TestBed.configureTestingModule({ imports: [StatusBadgeComponent] });
    const fixture = TestBed.createComponent(StatusBadgeComponent);
    fixture.componentRef.setInput('status', 'non_conformant');
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent?.trim()).toBe('Não conforme');
  });

  it('renders a distinct label for a run with zero entities found', () => {
    TestBed.configureTestingModule({ imports: [StatusBadgeComponent] });
    const fixture = TestBed.createComponent(StatusBadgeComponent);
    fixture.componentRef.setInput('status', 'no_entities_found');
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent?.trim()).toBe('Nenhuma entidade encontrada');
  });
});
