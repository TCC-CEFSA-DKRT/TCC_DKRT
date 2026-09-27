import { TestBed } from '@angular/core/testing';
import { Router, UrlTree } from '@angular/router';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { firstValueFrom, isObservable } from 'rxjs';

import { appGuard } from './app.guard';
import { API_CONFIG, DEFAULT_API_CONFIG } from './api-config';
import { SessionService } from './session.service';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

async function runGuard(): Promise<boolean | UrlTree> {
  const result = TestBed.runInInjectionContext(() => appGuard({} as never, {} as never));
  const resolved = isObservable(result) ? await firstValueFrom(result) : result;
  return resolved as boolean | UrlTree;
}

describe('appGuard', () => {
  let httpMock: HttpTestingController;
  let session: SessionService;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
    session = TestBed.inject(SessionService);
    router = TestBed.inject(Router);
  });

  afterEach(() => httpMock.verify());

  it('allows navigation without a request when the session is already cached with a tenant', async () => {
    session.session.set({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    const result = await runGuard();

    expect(result).toBe(true);
    httpMock.expectNone(`${BASE_URL}/session`);
  });

  it('loads /session and allows navigation when it returns a tenant', async () => {
    const promise = runGuard();
    httpMock.expectOne(`${BASE_URL}/session`).flush({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    expect(await promise).toBe(true);
  });

  it('redirects to /login when saas has no tenant', async () => {
    const promise = runGuard();
    httpMock.expectOne(`${BASE_URL}/session`).flush({ deployment_mode: 'saas', tenant: null });

    const result = await promise;
    expect(result).toEqual(router.parseUrl('/login'));
  });

  it('redirects to /config when self-hosted has no tenant', async () => {
    const promise = runGuard();
    httpMock
      .expectOne(`${BASE_URL}/session`)
      .flush({ deployment_mode: 'selfhosted', tenant: null });

    const result = await promise;
    expect(result).toEqual(router.parseUrl('/config'));
  });

  it('fails open (allows navigation) when /session errors out', async () => {
    const promise = runGuard();
    httpMock.expectOne(`${BASE_URL}/session`).flush('boom', { status: 500, statusText: 'Error' });

    expect(await promise).toBe(true);
  });
});
