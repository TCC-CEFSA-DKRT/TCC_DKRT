import {
  EntityReportResponse,
  RecommendationResponse,
  ViolationResponse,
} from '../../shared/interfaces/audit.interface';
import {
  EntityReportView,
  RecommendationView,
  SeverityGroupView,
} from './report-detail.interface';
import { ACTION_LABELS, RULE_LABELS, SEVERITY_GROUP_TITLES, SEVERITY_ORDER } from './report-labels';

export function ruleLabel(rule: string): string {
  const known = RULE_LABELS[rule];
  if (known) {
    return known;
  }
  const readable = rule.replace(/[_-]+/g, ' ').trim();
  return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : rule;
}

export function normalizeAttributePath(path: string): string {
  return path.trim().toLowerCase();
}

export function entityTrackKey(report: EntityReportResponse): string {
  return `${report.entity_type}:${report.entity_id}`;
}

export function toEntityReportView(report: EntityReportResponse): EntityReportView {
  const pending = [...report.recommendations];
  const takeRecommendationsFor = (violation: ViolationResponse): RecommendationView[] => {
    const target = normalizeAttributePath(violation.attribute_path);
    const matched = pending.filter((rec) => normalizeAttributePath(rec.attribute_path) === target);
    for (const rec of matched) {
      pending.splice(pending.indexOf(rec), 1);
    }
    return matched.map((rec) => toRecommendationView(rec, true));
  };

  const groups: SeverityGroupView[] = SEVERITY_ORDER.map((severity) => ({
    severity,
    title: SEVERITY_GROUP_TITLES[severity],
    items: report.violations
      .filter((violation) => violation.severity === severity)
      .map((violation) => ({
        violation,
        ruleLabel: ruleLabel(violation.rule),
        recommendations: takeRecommendationsFor(violation),
      })),
  })).filter((group) => group.items.length > 0);

  return {
    report,
    groups,
    otherRecommendations: pending.map((rec) => toRecommendationView(rec, false)),
    validated: report.status !== 'no_model_found' && report.status !== 'schema_unavailable',
  };
}

export function toRecommendationView(
  rec: RecommendationResponse,
  attachedToViolation: boolean
): RecommendationView {
  return {
    actionLabel: ACTION_LABELS[rec.action] ?? rec.action,
    rationale: rec.rationale,
    confidencePercent: Math.round(rec.confidence * 100),
    attachedToViolation,
    attributePath: rec.attribute_path,
    proposedPatch: rec.proposed_patch,
    proposedPatchText: JSON.stringify(rec.proposed_patch, null, 2),
  };
}
