import { EMAIL_PATTERN, LOGIN_MESSAGES } from './login.constants';
import { LoginFieldErrors } from './login.interface';

export function validateLogin(email: string, password: string): LoginFieldErrors {
  const errors: LoginFieldErrors = {};
  const trimmedEmail = email.trim();
  if (!trimmedEmail) {
    errors.email = LOGIN_MESSAGES.emailRequired;
  } else if (!EMAIL_PATTERN.test(trimmedEmail)) {
    errors.email = LOGIN_MESSAGES.emailFormat;
  }
  if (!password) {
    errors.password = LOGIN_MESSAGES.passwordRequired;
  }
  return errors;
}
