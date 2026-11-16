import { LoginField } from './login.interface';

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const LOGIN_MESSAGES = {
  emailRequired: 'Informe o email.',
  emailFormat: 'Use um email no formato nome@dominio.com.',
  passwordRequired: 'Informe a senha.',
  invalidCredentials: 'Email ou senha inválidos.',
  unavailable: 'Não foi possível entrar. Tente novamente.',
  sessionExpired: 'Sua sessão expirou. Entre novamente para continuar de onde parou.',
};

export const LOGIN_INPUT_IDS: Record<LoginField, string> = {
  email: 'login-email',
  password: 'login-password',
};
