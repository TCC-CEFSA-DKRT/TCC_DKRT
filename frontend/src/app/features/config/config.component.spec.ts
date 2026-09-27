import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

import { ConfigComponent } from './config.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';
import { SessionService } from '../../core/session.service';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

describe('ConfigComponent', () => {
  let httpMock: HttpTestingController;
  let router: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    router = jasmine.createSpyObj<Router>('Router', ['navigateByUrl']);
    await TestBed.configureTestingModule({
      imports: [ConfigComponent],
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

  function createAndPrefill() {
    const fixture = TestBed.createComponent(ConfigComponent);
    const component = fixture.componentInstance as any;
    httpMock.expectOne(`${BASE_URL}/config`).flush({
      configured: false,
      broker_url: 'http://orion:1026',
      fiware_service: 'openiot',
      fiware_service_path: '/',
    });
    fixture.detectChanges();
    return { fixture, component };
  }

  it('prefills the form from GET /config on creation', () => {
    const { component } = createAndPrefill();
    expect(component.brokerUrl).toBe('http://orion:1026');
    expect(component.fiwareService).toBe('openiot');
    expect(component.loadState()).toBe('ready');
  });

  it('shows an error state with retry when GET /config fails', () => {
    const fixture = TestBed.createComponent(ConfigComponent);
    const component = fixture.componentInstance as any;
    httpMock.expectOne(`${BASE_URL}/config`).flush('boom', { status: 500, statusText: 'Error' });
    fixture.detectChanges();

    expect(component.loadState()).toBe('error');

    component.fetchConfig();
    httpMock.expectOne(`${BASE_URL}/config`).flush({
      configured: false,
      broker_url: 'http://orion:1026',
      fiware_service: 'openiot',
      fiware_service_path: '/',
    });
    expect(component.loadState()).toBe('ready');
  });

  it('sends exactly broker_url/fiware_service/fiware_service_path on save', () => {
    const { component } = createAndPrefill();
    component.brokerUrl = 'http://orion:1026';
    component.fiwareService = 'openiot';
    component.fiwareServicePath = '/prod';
    component.onSave();

    const putReq = httpMock.expectOne(`${BASE_URL}/config`);
    expect(putReq.request.method).toBe('PUT');
    expect(putReq.request.body).toEqual({
      broker_url: 'http://orion:1026',
      fiware_service: 'openiot',
      fiware_service_path: '/prod',
    });
    putReq.flush({
      configured: true,
      broker_url: 'http://orion:1026',
      fiware_service: 'openiot',
      fiware_service_path: '/prod',
    });

    httpMock.expectOne(`${BASE_URL}/entity-types`).flush({ types: [], broker_reachable: true });
  });

  it('shows the entity type count when the broker is reachable after saving', () => {
    const { fixture, component } = createAndPrefill();
    component.onSave();
    httpMock.expectOne(`${BASE_URL}/config`).flush({
      configured: true,
      broker_url: 'http://orion:1026',
      fiware_service: 'openiot',
      fiware_service_path: '/',
    });
    httpMock
      .expectOne(`${BASE_URL}/entity-types`)
      .flush({ types: ['AirQualityObserved', 'Streetlight'], broker_reachable: true });
    fixture.detectChanges();

    expect(component.connectionTest()).toEqual({ status: 'ok', count: 2 });
    const message: HTMLElement = fixture.nativeElement.querySelector('.connection-test--ok');
    expect(message.textContent).toContain('2 tipo(s)');
    expect(fixture.nativeElement.querySelector('.config-continue')).not.toBeNull();
  });

  it('shows a warning (but still lets the user continue) when the broker is unreachable', () => {
    const { fixture, component } = createAndPrefill();
    component.onSave();
    httpMock.expectOne(`${BASE_URL}/config`).flush({
      configured: true,
      broker_url: 'http://orion:1026',
      fiware_service: 'openiot',
      fiware_service_path: '/',
    });
    httpMock.expectOne(`${BASE_URL}/entity-types`).flush({ types: [], broker_reachable: false });
    fixture.detectChanges();

    expect(component.connectionTest()).toEqual({ status: 'warn' });
    expect(fixture.nativeElement.querySelector('.connection-test--warn')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.config-continue')).not.toBeNull();
  });

  it('updates the session tenant from the PUT /config response, without refetching /session', () => {
    const { component } = createAndPrefill();
    const session = TestBed.inject(SessionService);
    session.session.set({ deployment_mode: 'selfhosted', tenant: null });

    component.onSave();
    httpMock.expectOne(`${BASE_URL}/config`).flush({
      configured: true,
      broker_url: 'http://orion:1026',
      fiware_service: 'novo-tenant',
      fiware_service_path: '/x',
    });
    httpMock.expectNone(`${BASE_URL}/session`);
    expect(session.session()).toEqual({
      deployment_mode: 'selfhosted',
      tenant: { fiware_service: 'novo-tenant', fiware_service_path: '/x' },
    });

    httpMock.expectOne(`${BASE_URL}/entity-types`).flush({ types: [], broker_reachable: true });
  });

  it('sends an empty fiware_service when the field is left blank', () => {
    const { component } = createAndPrefill();
    component.brokerUrl = 'http://orion:1026';
    component.fiwareService = '';
    component.fiwareServicePath = '/';
    component.onSave();

    const putReq = httpMock.expectOne(`${BASE_URL}/config`);
    expect(putReq.request.body).toEqual({
      broker_url: 'http://orion:1026',
      fiware_service: '',
      fiware_service_path: '/',
    });
    putReq.flush({
      configured: true,
      broker_url: 'http://orion:1026',
      fiware_service: '',
      fiware_service_path: '/',
    });

    const session = TestBed.inject(SessionService);
    expect(session.session()?.tenant?.fiware_service).toBe('');

    httpMock.expectOne(`${BASE_URL}/entity-types`).flush({ types: [], broker_reachable: true });
  });

  it('onContinue() navigates to /dashboard', () => {
    const { component } = createAndPrefill();
    component.onContinue();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard');
  });
});
