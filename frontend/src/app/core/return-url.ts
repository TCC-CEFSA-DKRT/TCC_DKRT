import { HOME_PATH, LOGIN_PATH } from './session.constants';

export function safeReturnUrl(url: string | null | undefined): string {
  if (!url || !url.startsWith('/') || url.startsWith('//') || url.startsWith(LOGIN_PATH)) {
    return HOME_PATH;
  }
  return url;
}
