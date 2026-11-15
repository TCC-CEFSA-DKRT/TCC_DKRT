import { TestBed } from '@angular/core/testing';

import { RecommendationView } from '../report-detail.models';
import { RecommendationCardComponent } from './recommendation-card.component';

function render(view: RecommendationView): HTMLElement {
  TestBed.configureTestingModule({ imports: [RecommendationCardComponent] });
  const fixture = TestBed.createComponent(RecommendationCardComponent);
  fixture.componentRef.setInput('view', view);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const BASE: RecommendationView = {
  actionLabel: 'Corrigir o formato',
  rationale: 'O modelo exige ISO 8601.',
  confidencePercent: 83,
  attachedToViolation: true,
  attributePath: 'dateLastLampChange',
  proposedPatch: { attribute: 'dateLastLampChange', value: '2026-10-24T00:00:00Z' },
  proposedPatchText: '{\n  "attribute": "dateLastLampChange"\n}',
};

describe('RecommendationCardComponent', () => {
  it('shows action, confidence, rationale and only the proposed fix when attached to a violation', () => {
    const element = render(BASE);
    const text = element.textContent ?? '';

    expect(text).toContain('Como corrigir: Corrigir o formato');
    expect(text).toContain('confiança 83%');
    expect(text).toContain('O modelo exige ISO 8601.');
    expect(element.querySelector('.recommendation__patch code')?.textContent).toContain('"attribute"');
    expect(element.querySelector('app-diff-view')).toBeNull();
  });

  it('compares the attribute with the proposed patch when it stands alone', () => {
    const element = render({ ...BASE, attachedToViolation: false });

    expect(element.querySelector('.recommendation__patch')).toBeNull();
    const diff = element.querySelector('app-diff-view')?.textContent ?? '';
    expect(diff).toContain('Atributo');
    expect(diff).toContain('dateLastLampChange');
    expect(diff).toContain('Correção proposta');
  });
});
