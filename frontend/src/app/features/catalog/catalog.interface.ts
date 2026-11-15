export type ViewState = 'loading' | 'loaded' | 'never_synced' | 'error';

export type ModelsState = 'idle' | 'loading' | 'loaded' | 'empty' | 'error';

export type SchemaState = 'loading' | 'loaded' | 'error';

export interface ExpandedSchema {
  key: string;
  state: SchemaState;
  content?: unknown;
  source?: string;
  fetchedAt?: string;
  error?: string;
}
