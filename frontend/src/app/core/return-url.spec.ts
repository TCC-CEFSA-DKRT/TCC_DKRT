import { safeReturnUrl } from './return-url';

describe('safeReturnUrl', () => {
  it('returns to the page inside the app the user was on', () => {
    expect(safeReturnUrl('/audit-runs/abc?status=failed')).toBe('/audit-runs/abc?status=failed');
  });

  it('goes to the dashboard when there is no page to return to', () => {
    expect(safeReturnUrl(null)).toBe('/dashboard');
    expect(safeReturnUrl('')).toBe('/dashboard');
  });

  it('never sends the user to another site after login', () => {
    expect(safeReturnUrl('https://site-falso.example/login')).toBe('/dashboard');
    expect(safeReturnUrl('//site-falso.example')).toBe('/dashboard');
  });

  it('does not loop back to the login page', () => {
    expect(safeReturnUrl('/login?reason=expired')).toBe('/dashboard');
  });
});
