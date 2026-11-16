import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

import { SessionService } from './session.service';
import { API_CONFIG, DEFAULT_API_CONFIG } from './api-config';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

describe('SessionService', () => {
  let service: SessionService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      ],
    });
    service = TestBed.inject(SessionService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('starts with no session loaded', () => {
    expect(service.session()).toBeNull();
  });

  it('load() fetches GET /session and stores the result in the signal', () => {
    service.load().subscribe();

    const req = httpMock.expectOne(`${BASE_URL}/session`);
    expect(req.request.method).toBe('GET');
    req.flush({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    expect(service.session()).toEqual({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });
  });

  it('login() posts credentials and then reloads the session', () => {
    service.login('user@example.com', 'secret').subscribe();

    const loginReq = httpMock.expectOne(`${BASE_URL}/auth/login`);
    expect(loginReq.request.method).toBe('POST');
    expect(loginReq.request.body).toEqual({ login_email: 'user@example.com', password: 'secret' });
    loginReq.flush({ access_token: 'ignored' });

    const sessionReq = httpMock.expectOne(`${BASE_URL}/session`);
    sessionReq.flush({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    expect(service.session()?.tenant).toEqual({ fiware_service: 'openiot', fiware_service_path: '/' });
  });

  it('login() propagates the error without reloading the session', () => {
    let failed = false;
    service.login('user@example.com', 'wrong').subscribe({ error: () => (failed = true) });

    httpMock.expectOne(`${BASE_URL}/auth/login`).flush(
      { detail: 'Email ou senha invalidos.' },
      { status: 401, statusText: 'Unauthorized' }
    );

    httpMock.expectNone(`${BASE_URL}/session`);
    expect(failed).toBe(true);
  });

  it('logout() posts to /auth/logout and clears the tenant, keeping the deployment mode', () => {
    service.load().subscribe();
    httpMock.expectOne(`${BASE_URL}/session`).flush({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    service.logout().subscribe();
    const req = httpMock.expectOne(`${BASE_URL}/auth/logout`);
    expect(req.request.method).toBe('POST');
    req.flush(null, { status: 204, statusText: 'No Content' });

    expect(service.session()?.deployment_mode).toBe('saas');
    expect(service.session()?.tenant).toBeNull();
  });

  describe('when the session expires', () => {
    let router: Router;

    beforeEach(() => {
      jasmine.clock().install();
      jasmine.clock().mockDate(new Date('2026-11-15T12:00:00Z'));
      router = TestBed.inject(Router);
      spyOn(router, 'navigate').and.resolveTo(true);
      spyOnProperty(router, 'url').and.returnValue('/audit-runs/abc');
    });

    afterEach(() => jasmine.clock().uninstall());

    function loadSaasSession(expiresAt: string): void {
      service.load().subscribe();
      httpMock.expectOne(`${BASE_URL}/session`).flush({
        deployment_mode: 'saas',
        tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
        expires_at: expiresAt,
      });
    }

    it('sends the user to the login with the expired notice and the page they were on', () => {
      loadSaasSession('2026-11-15T12:30:00Z');

      jasmine.clock().tick(30 * 60 * 1000);

      expect(service.session()?.tenant).toBeNull();
      expect(router.navigate).toHaveBeenCalledWith(['/login'], {
        queryParams: { reason: 'expired', returnUrl: '/audit-runs/abc' },
      });
    });

    it('does nothing before the expiration time', () => {
      loadSaasSession('2026-11-15T12:30:00Z');

      jasmine.clock().tick(29 * 60 * 1000);

      expect(service.session()?.tenant).not.toBeNull();
      expect(router.navigate).not.toHaveBeenCalled();
    });

    it('stops the countdown after logout', () => {
      loadSaasSession('2026-11-15T12:30:00Z');
      service.logout().subscribe();
      httpMock.expectOne(`${BASE_URL}/auth/logout`).flush(null, { status: 204, statusText: 'No Content' });

      jasmine.clock().tick(31 * 60 * 1000);

      expect(router.navigate).not.toHaveBeenCalled();
    });

    it('never schedules an expiration in self-hosted mode', () => {
      service.load().subscribe();
      httpMock.expectOne(`${BASE_URL}/session`).flush({
        deployment_mode: 'selfhosted',
        tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
        expires_at: '2026-11-15T12:00:01Z',
      });

      jasmine.clock().tick(60 * 1000);

      expect(service.session()?.tenant).not.toBeNull();
      expect(router.navigate).not.toHaveBeenCalled();
    });
  });
});
