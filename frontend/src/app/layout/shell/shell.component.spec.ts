import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';

import { ShellComponent } from './shell.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';
import { SessionService } from '../../core/session.service';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

describe('ShellComponent', () => {
  let httpMock: HttpTestingController;
  let session: SessionService;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ShellComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
    session = TestBed.inject(SessionService);
    router = TestBed.inject(Router);
    spyOn(router, 'navigateByUrl').and.resolveTo(true);
  });

  afterEach(() => httpMock.verify());

  it('shows the "Configuração" link only in self-hosted mode', () => {
    session.session.set({ deployment_mode: 'saas', tenant: { fiware_service: 'openiot', fiware_service_path: '/' } });
    const fixture = TestBed.createComponent(ShellComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Configuração');

    session.session.set({ deployment_mode: 'selfhosted', tenant: { fiware_service: 'openiot', fiware_service_path: '/' } });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Configuração');
  });

  it('shows the tenant name and a "Sair" button only in saas mode', () => {
    session.session.set({ deployment_mode: 'selfhosted', tenant: { fiware_service: 'openiot', fiware_service_path: '/' } });
    const fixture = TestBed.createComponent(ShellComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.shell__logout')).toBeNull();

    session.session.set({ deployment_mode: 'saas', tenant: { fiware_service: 'acme', fiware_service_path: '/' } });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.shell__tenant').textContent).toContain('acme');
    expect(fixture.nativeElement.querySelector('.shell__logout')).not.toBeNull();
  });

  it('logging out calls POST /auth/logout and navigates to /login', () => {
    session.session.set({ deployment_mode: 'saas', tenant: { fiware_service: 'acme', fiware_service_path: '/' } });
    const fixture = TestBed.createComponent(ShellComponent);
    fixture.detectChanges();

    (fixture.nativeElement.querySelector('.shell__logout') as HTMLButtonElement).click();
    httpMock.expectOne(`${BASE_URL}/auth/logout`).flush(null, { status: 204, statusText: 'No Content' });

    expect(router.navigateByUrl).toHaveBeenCalledWith('/login');
    expect(session.session()?.tenant).toBeNull();
  });
});
