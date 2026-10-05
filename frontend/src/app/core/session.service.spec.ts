import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';

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

    expect(service.session()).toEqual({ deployment_mode: 'saas', tenant: null });
  });
});
