import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { Router } from '@angular/router';

import { tenantInterceptor } from './tenant.interceptor';
import { API_CONFIG, DEFAULT_API_CONFIG } from './api-config';
import { SessionService } from './session.service';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

describe('tenantInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let session: SessionService;
  let router: jasmine.SpyObj<Router>;

  beforeEach(() => {
    router = jasmine.createSpyObj<Router>('Router', ['navigateByUrl']);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([tenantInterceptor])),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
        { provide: Router, useValue: router },
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    session = TestBed.inject(SessionService);
  });

  afterEach(() => httpMock.verify());

  it('sends withCredentials for a request to the API', () => {
    http.get(`${BASE_URL}/audits`).subscribe();
    const req = httpMock.expectOne(`${BASE_URL}/audits`);
    expect(req.request.withCredentials).toBe(true);
    req.flush([]);
  });

  it('leaves a request to another origin untouched', () => {
    http.get('https://fonts.googleapis.com/css').subscribe();
    const req = httpMock.expectOne('https://fonts.googleapis.com/css');
    expect(req.request.withCredentials).toBe(false);
    req.flush({});
  });

  it('attaches Fiware-Service/Fiware-ServicePath from the session in self-hosted mode', () => {
    session.session.set({
      deployment_mode: 'selfhosted',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/prod' },
    });

    http.get(`${BASE_URL}/audits`).subscribe();
    const req = httpMock.expectOne(`${BASE_URL}/audits`);
    expect(req.request.headers.get('Fiware-Service')).toBe('openiot');
    expect(req.request.headers.get('Fiware-ServicePath')).toBe('/prod');
    req.flush([]);
  });

  it('does not attach tenant headers in saas mode', () => {
    session.session.set({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    http.get(`${BASE_URL}/audits`).subscribe();
    const req = httpMock.expectOne(`${BASE_URL}/audits`);
    expect(req.request.headers.has('Fiware-Service')).toBe(false);
    req.flush([]);
  });

  it('on a 401 in saas mode, clears the session tenant and redirects to /login', () => {
    session.session.set({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    let failed = false;
    http.get(`${BASE_URL}/audits`).subscribe({ error: () => (failed = true) });
    httpMock
      .expectOne(`${BASE_URL}/audits`)
      .flush({ detail: 'Sessao ausente' }, { status: 401, statusText: 'Unauthorized' });

    expect(failed).toBe(true);
    expect(session.session()?.tenant).toBeNull();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/login');
  });

  it('a 401 from /auth/login itself never triggers a redirect', () => {
    session.session.set({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    http.post(`${BASE_URL}/auth/login`, {}).subscribe({ error: () => {} });
    httpMock
      .expectOne(`${BASE_URL}/auth/login`)
      .flush({ detail: 'Email ou senha invalidos.' }, { status: 401, statusText: 'Unauthorized' });

    expect(router.navigateByUrl).not.toHaveBeenCalled();
  });

  it('a 401 in self-hosted mode never redirects to /login', () => {
    session.session.set({
      deployment_mode: 'selfhosted',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    http.get(`${BASE_URL}/audits`).subscribe({ error: () => {} });
    httpMock
      .expectOne(`${BASE_URL}/audits`)
      .flush({ detail: 'Fiware-Service ausente' }, { status: 401, statusText: 'Unauthorized' });

    expect(router.navigateByUrl).not.toHaveBeenCalled();
  });
});
