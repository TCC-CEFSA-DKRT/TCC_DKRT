export type LoginState = 'idle' | 'submitting' | 'error';

export type LoginField = 'email' | 'password';

export type LoginFieldErrors = Partial<Record<LoginField, string>>;
