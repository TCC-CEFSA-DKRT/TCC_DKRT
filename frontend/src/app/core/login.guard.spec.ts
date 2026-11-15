import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRouteSnapshot, Router, UrlTree, convertToParamMap } from '@angular/router';
import { firstValueFrom, isObservable } from 'rxjs';

import { API_CONFIG, DEFAULT_API_CONFIG } from './api-config';
import { loginGuard } from './login.guard';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

describe('loginGuard', () => {
  let httpMock: HttpTestingController;
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
    router = TestBed.inject(Router);
  });

  afterEach(() => httpMock.verify());

  async function runGuard(returnUrl: string | null, session: object | 'error'): Promise<boolean | UrlTree> {
    const route = { queryParamMap: convertToParamMap(returnUrl ? { returnUrl } : {}) } as ActivatedRouteSnapshot;
    const result = TestBed.runInInjectionContext(() => loginGuard(route, {} as never));
    const promise = isObservable(result) ? firstValueFrom(result) : Promise.resolve(result);
    const request = httpMock.expectOne(`${BASE_URL}/session`);
    if (session === 'error') {
      request.flush('boom', { status: 500, statusText: 'Error' });
    } else {
      request.flush(session);
    }
    return (await promise) as boolean | UrlTree;
  }

  it('shows the login to a saas visitor without a session', async () => {
    expect(await runGuard(null, { deployment_mode: 'saas', tenant: null })).toBe(true);
  });

  it('sends a user who is already logged in back to the page they asked for', async () => {
    const result = await runGuard('/catalog', {
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    expect(result).toEqual(router.parseUrl('/catalog'));
  });

  it('has no login in self-hosted mode and opens the dashboard instead', async () => {
    const result = await runGuard(null, {
      deployment_mode: 'selfhosted',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    expect(result).toEqual(router.parseUrl('/dashboard'));
  });

  it('still shows the login when the session cannot be checked', async () => {
    expect(await runGuard(null, 'error')).toBe(true);
  });
});
