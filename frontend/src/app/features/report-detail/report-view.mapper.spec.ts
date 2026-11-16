import { EntityReportResponse, ViolationResponse } from '../../shared/interfaces/audit.interface';
import { RULE_LABELS } from './report-labels';
import {
  entityTrackKey,
  normalizeAttributePath,
  ruleLabel,
  toEntityReportView,
} from './report-view.mapper';

function violation(overrides: Partial<ViolationResponse>): ViolationResponse {
  return {
    attribute_path: 'status',
    severity: 'error',
    rule: 'enum_violation',
    expected: null,
    found: null,
    message: 'm',
    detected_by: 'structural',
    ...overrides,
  };
}

function report(overrides: Partial<EntityReportResponse> = {}): EntityReportResponse {
  return {
    entity_id: 'urn:1',
    entity_type: 'Streetlight',
    status: 'non_conformant',
    semantic_analysis_skipped: false,
    violations: [],
    recommendations: [],
    ...overrides,
  };
}

describe('report-view.mapper', () => {
  describe('ruleLabel', () => {
    it('translates every Level 1 rule to Portuguese', () => {
      expect(ruleLabel('required_property_missing')).toBe('Atributo obrigatório ausente');
      expect(ruleLabel('type_mismatch')).toBe('Tipo de dado incorreto');
      expect(ruleLabel('format_invalid')).toBe('Formato inválido');
      expect(ruleLabel('value_out_of_range')).toBe('Valor fora do intervalo permitido');
      expect(ruleLabel('enum_violation')).toBe('Valor fora da lista permitida');
      expect(ruleLabel('unexpected_property')).toBe('Atributo não previsto no modelo');
      expect(ruleLabel('malformed_attribute')).toBe('Atributo fora do formato NGSI-v2');
      expect(ruleLabel('attribute_name_synonym')).toBe('Nome de atributo diferente do definido no modelo');
      for (const [rule, label] of Object.entries(RULE_LABELS)) {
        expect(ruleLabel(rule)).toBe(label);
      }
    });

    it('turns an unknown SLM rule into readable text', () => {
      expect(ruleLabel('generic_description')).toBe('Generic description');
      expect(ruleLabel('unit-mismatch')).toBe('Unit mismatch');
      expect(ruleLabel('___')).toBe('___');
    });
  });

  describe('normalizeAttributePath', () => {
    it('ignores surrounding spaces and letter case', () => {
      expect(normalizeAttributePath('  LampHeight ')).toBe('lampheight');
    });
  });

  describe('entityTrackKey', () => {
    it('combines type and id, the NGSI-v2 identity of an entity', () => {
      const a = entityTrackKey(report({ entity_id: 'urn:1', entity_type: 'Streetlight' }));
      const b = entityTrackKey(report({ entity_id: 'urn:1', entity_type: 'WeatherObserved' }));
      expect(a).toBe('Streetlight:urn:1');
      expect(a).not.toBe(b);
    });
  });

  describe('toEntityReportView', () => {
    it('matches a recommendation whose attribute differs only in case or spaces', () => {
      const view = toEntityReportView(
        report({
          violations: [violation({ attribute_path: 'lampHeight' })],
          recommendations: [
            {
              attribute_path: ' LAMPHEIGHT',
              action: 'rename_attribute',
              proposed_patch: { from: 'lampHeight', to: 'lanternHeight' },
              rationale: 'sinônimo',
              confidence: 0.9,
            },
          ],
        })
      );

      expect(view.groups[0].items[0].recommendations.length).toBe(1);
      expect(view.groups[0].items[0].recommendations[0].attachedToViolation).toBeTrue();
      expect(view.otherRecommendations.length).toBe(0);
    });

    it('keeps recommendations without a matching violation under other recommendations', () => {
      const view = toEntityReportView(
        report({
          status: 'partial',
          recommendations: [
            {
              attribute_path: 'temp',
              action: 'rename_attribute',
              proposed_patch: { from: 'temp', to: 'temperature' },
              rationale: 'sinônimo',
              confidence: 0.75,
            },
          ],
        })
      );

      expect(view.groups.length).toBe(0);
      expect(view.otherRecommendations.length).toBe(1);
      expect(view.otherRecommendations[0].attachedToViolation).toBeFalse();
      expect(view.otherRecommendations[0].confidencePercent).toBe(75);
    });

    it('gives the recommendation to the most severe of two findings on the same attribute', () => {
      const view = toEntityReportView(
        report({
          violations: [
            violation({ severity: 'warning', rule: 'attribute_name_synonym' }),
            violation({ severity: 'error' }),
          ],
          recommendations: [
            {
              attribute_path: 'status',
              action: 'fix_format',
              proposed_patch: { attribute: 'status', value: 'ok' },
              rationale: 'r',
              confidence: 0.8,
            },
          ],
        })
      );

      expect(view.groups.map((group) => group.severity)).toEqual(['error', 'warning']);
      expect(view.groups[0].items[0].recommendations.length).toBe(1);
      expect(view.groups[1].items[0].recommendations.length).toBe(0);
    });

    it('marks entities without model or schema as not validated', () => {
      expect(toEntityReportView(report({ status: 'no_model_found' })).validated).toBeFalse();
      expect(toEntityReportView(report({ status: 'schema_unavailable' })).validated).toBeFalse();
      expect(toEntityReportView(report({ status: 'conformant' })).validated).toBeTrue();
    });
  });
});
