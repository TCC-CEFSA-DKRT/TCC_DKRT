import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';

import { LoginComponent } from './login.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;
const LOGGED_SESSION = {
  deployment_mode: 'saas',
  tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
  expires_at: null,
};

describe('LoginComponent', () => {
  let httpMock: HttpTestingController;
  let router: jasmine.SpyObj<Router>;

  async function render(queryParams: Record<string, string> = {}) {
    router = jasmine.createSpyObj<Router>('Router', ['navigateByUrl', 'navigate'], { url: '/login' });
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
        { provide: Router, useValue: router },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap(queryParams) } } },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(LoginComponent);
    const element: HTMLElement = fixture.nativeElement;
    const refresh = async () => {
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
    };
    await refresh();
    return {
      text: () => element.textContent ?? '',
      query: <T extends Element>(selector: string) => element.querySelector<T>(selector),
      type: async (selector: string, value: string) => {
        const input = element.querySelector<HTMLInputElement>(selector)!;
        input.value = value;
        input.dispatchEvent(new Event('input'));
        await refresh();
      },
      submit: async () => {
        element.querySelector<HTMLButtonElement>('.login-submit')!.click();
        await refresh();
      },
      refresh,
    };
  }

  afterEach(() => httpMock.verify());

  describe('validation before calling the API', () => {
    it('asks for the email and the password when both are empty', async () => {
      const { submit, text, query } = await render();

      await submit();

      httpMock.expectNone(`${BASE_URL}/auth/login`);
      expect(text()).toContain('Informe o email.');
      expect(text()).toContain('Informe a senha.');
      expect(query('#login-email')!.getAttribute('aria-invalid')).toBe('true');
      expect(document.activeElement?.id).toBe('login-email');
    });

    it('rejects an email without the domain part', async () => {
      const { type, submit, text } = await render();
      await type('#login-email', 'usuario@');
      await type('#login-password', 'segredo');

      await submit();

      httpMock.expectNone(`${BASE_URL}/auth/login`);
      expect(text()).toContain('Use um email no formato nome@dominio.com.');
    });
  });

  describe('signing in', () => {
    it('sends the credentials and opens the dashboard', async () => {
      const { type, submit, refresh } = await render();
      await type('#login-email', ' user@example.com ');
      await type('#login-password', 'secret');

      await submit();
      const request = httpMock.expectOne(`${BASE_URL}/auth/login`);
      expect(request.request.body).toEqual({ login_email: 'user@example.com', password: 'secret' });
      request.flush({ access_token: 'ignored' });
      httpMock.expectOne(`${BASE_URL}/session`).flush(LOGGED_SESSION);
      await refresh();

      expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard');
    });

    it('returns to the page the user was on before the session expired', async () => {
      const { type, submit, refresh } = await render({ reason: 'expired', returnUrl: '/audit-runs/abc' });
      await type('#login-email', 'user@example.com');
      await type('#login-password', 'secret');

      await submit();
      httpMock.expectOne(`${BASE_URL}/auth/login`).flush({ access_token: 'ignored' });
      httpMock.expectOne(`${BASE_URL}/session`).flush(LOGGED_SESSION);
      await refresh();

      expect(router.navigateByUrl).toHaveBeenCalledWith('/audit-runs/abc');
    });

    it('ignores a return address outside the app', async () => {
      const { type, submit, refresh } = await render({ returnUrl: 'https://site-falso.example' });
      await type('#login-email', 'user@example.com');
      await type('#login-password', 'secret');

      await submit();
      httpMock.expectOne(`${BASE_URL}/auth/login`).flush({ access_token: 'ignored' });
      httpMock.expectOne(`${BASE_URL}/session`).flush(LOGGED_SESSION);
      await refresh();

      expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard');
    });

    it('says the email or password is wrong on a 401, without telling which', async () => {
      const { type, submit, refresh, text, query } = await render();
      await type('#login-email', 'user@example.com');
      await type('#login-password', 'errada');

      await submit();
      httpMock
        .expectOne(`${BASE_URL}/auth/login`)
        .flush({ detail: 'Email ou senha invalidos.' }, { status: 401, statusText: 'Unauthorized' });
      await refresh();

      expect(text()).toContain('Email ou senha inválidos.');
      expect(query<HTMLButtonElement>('.login-submit')!.disabled).toBeFalse();
      expect(router.navigateByUrl).not.toHaveBeenCalled();
    });

    it('shows a generic message when the API is unavailable', async () => {
      const { type, submit, refresh, text } = await render();
      await type('#login-email', 'user@example.com');
      await type('#login-password', 'secret');

      await submit();
      httpMock.expectOne(`${BASE_URL}/auth/login`).flush('boom', { status: 503, statusText: 'Unavailable' });
      await refresh();

      expect(text()).toContain('Não foi possível entrar. Tente novamente.');
    });

    it('blocks a second click while the first attempt is in flight', async () => {
      const { type, submit, query } = await render();
      await type('#login-email', 'user@example.com');
      await type('#login-password', 'secret');

      await submit();
      await submit();

      expect(query<HTMLButtonElement>('.login-submit')!.disabled).toBeTrue();
      httpMock.expectOne(`${BASE_URL}/auth/login`).flush({ access_token: 'ignored' });
      httpMock.expectOne(`${BASE_URL}/session`).flush(LOGGED_SESSION);
    });
  });

  describe('expired session', () => {
    it('explains that the session expired', async () => {
      const { text } = await render({ reason: 'expired' });

      expect(text()).toContain('Sua sessão expirou. Entre novamente para continuar de onde parou.');
    });

    it('does not show the notice on a normal visit', async () => {
      const { text } = await render();

      expect(text()).not.toContain('Sua sessão expirou');
    });
  });
});
