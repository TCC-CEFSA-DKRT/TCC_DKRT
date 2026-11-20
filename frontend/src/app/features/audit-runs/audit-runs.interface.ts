import { RunStatus } from '../../shared/interfaces/audit.interface';

export type ViewState = 'loading' | 'loaded' | 'empty' | 'error';

export interface RunStatusOption {
  value: RunStatus;
  label: string;
}
