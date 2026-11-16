export type LoadState = 'loading' | 'ready' | 'error';

export type SaveState = 'idle' | 'saving' | 'error';

export type ConnectionTest = { status: 'ok'; count: number } | { status: 'warn' } | null;
