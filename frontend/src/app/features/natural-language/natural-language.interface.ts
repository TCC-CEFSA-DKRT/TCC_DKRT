export type InterpretState = 'idle' | 'loading' | 'interpreted' | 'error';

export type ConfirmState = 'idle' | 'submitting' | 'submitted' | 'error';

export type ResultView = 'ready' | 'clarify' | 'discovery' | 'out-of-scope' | 'unavailable';

export type ConfidenceLevel = 'alta' | 'media' | 'baixa';

export type NaturalLanguageAction = 'interpret' | 'confirm';
