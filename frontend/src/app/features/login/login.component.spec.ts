import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

import { LoginComponent } from './login.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

describe('LoginComponent', () => {
  let httpMock: HttpTestingController;
  let router: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    router = jasmine.createSpyObj<Router>('Router', ['navigateByUrl']);
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
        { provide: Router, useValue: router },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('logs in, reloads the session and navigates to /dashboard on success', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    const component = fixture.componentInstance as any;
    component.email = 'user@example.com';
    component.password = 'secret';
    component.onSubmit();

    expect(component.state()).toBe('submitting');

    const loginReq = httpMock.expectOne(`${BASE_URL}/auth/login`);
    expect(loginReq.request.body).toEqual({ login_email: 'user@example.com', password: 'secret' });
    loginReq.flush({ access_token: 'ignored' });

    httpMock.expectOne(`${BASE_URL}/session`).flush({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'openiot', fiware_service_path: '/' },
    });

    expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard');
  });

  it('shows "Email ou senha inválidos." on a 401 and re-enables the submit button', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    const component = fixture.componentInstance as any;
    component.email = 'user@example.com';
    component.password = 'wrong';
    component.onSubmit();

    httpMock
      .expectOne(`${BASE_URL}/auth/login`)
      .flush({ detail: 'Email ou senha invalidos.' }, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges();

    expect(component.state()).toBe('error');
    expect(component.errorMessage()).toBe('Email ou senha inválidos.');
    expect(router.navigateByUrl).not.toHaveBeenCalled();

    const button: HTMLButtonElement = fixture.nativeElement.querySelector('.login-submit');
    expect(button.disabled).toBe(false);
  });

  it('shows a generic error message for a non-401 failure', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    const component = fixture.componentInstance as any;
    component.email = 'user@example.com';
    component.password = 'secret';
    component.onSubmit();

    httpMock
      .expectOne(`${BASE_URL}/auth/login`)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('Não foi possível entrar. Tente novamente.');
  });

  it('disables the submit button while the request is in flight', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance as any;
    component.email = 'user@example.com';
    component.password = 'secret';
    component.onSubmit();
    fixture.detectChanges();

    const button: HTMLButtonElement = fixture.nativeElement.querySelector('.login-submit');
    expect(button.disabled).toBe(true);

    httpMock.expectOne(`${BASE_URL}/auth/login`).flush({ access_token: 'ignored' });
    httpMock.expectOne(`${BASE_URL}/session`).flush({ deployment_mode: 'saas', tenant: null });
  });
});
