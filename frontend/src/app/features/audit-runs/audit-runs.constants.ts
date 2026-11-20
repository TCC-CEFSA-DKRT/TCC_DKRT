import { BADGE_STYLES } from '../../shared/components/status-badge/status-badge.constants';
import { RunStatus } from '../../shared/interfaces/audit.interface';
import { RunStatusOption } from './audit-runs.interface';

const FILTERABLE_RUN_STATUSES: RunStatus[] = [
  'queued',
  'running',
  'completed',
  'partial',
  'failed',
  'no_entities_found',
];

export const RUN_STATUS_OPTIONS: readonly RunStatusOption[] = FILTERABLE_RUN_STATUSES.map((value) => ({
  value,
  label: BADGE_STYLES[value].label,
}));
