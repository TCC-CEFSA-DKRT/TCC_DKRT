import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

import { ConfigComponent } from './config.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';
import { SessionService } from '../../core/session.service';
import {
  BrokerConfigResponse,
  BrokerConnectionTestResponse,
} from '../../shared/interfaces/config.interface';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

const LOADED: BrokerConfigResponse = {
  configured: false,
  broker_url: 'http://localhost:1026',
  fiware_service: 'openiot',
  fiware_service_path: '/',
  broker_kind: 'local',
  ngsi_version: 'v2',
  has_api_key: false,
  default_local_broker_url: 'http://localhost:1026',
  connection: null,
};

const REACHABLE: BrokerConnectionTestResponse = { status: 'ok', entity_types_count: 2, http_status: 200 };

function failure(status: BrokerConnectionTestResponse['status'], httpStatus: number | null = null) {
  return { status, entity_types_count: null, http_status: httpStatus } as BrokerConnectionTestResponse;
}

function savedResponse(overrides: Partial<BrokerConfigResponse> = {}): BrokerConfigResponse {
  return { ...LOADED, configured: true, connection: REACHABLE, ...overrides };
}

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

  async function render(loaded: BrokerConfigResponse = LOADED) {
    const fixture = TestBed.createComponent(ConfigComponent);
    const element: HTMLElement = fixture.nativeElement;
    const refresh = async () => {
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
    };
    httpMock.expectOne(`${BASE_URL}/config`).flush(loaded);
    await refresh();

    const query = <T extends Element>(selector: string) => element.querySelector<T>(selector);
    const inputValue = (selector: string) => query<HTMLInputElement>(selector)!.value;
    const type = async (selector: string, value: string) => {
      const input = query<HTMLInputElement>(selector)!;
      input.value = value;
      input.dispatchEvent(new Event('input'));
      await refresh();
    };
    const click = async (selector: string) => {
      query<HTMLElement>(selector)!.click();
      await refresh();
    };
    const respond = async (url: string, body: object | string, status = 200) => {
      const request = httpMock.expectOne(url);
      request.flush(body, { status, statusText: status === 200 ? 'OK' : 'Error' });
      await refresh();
      return request;
    };
    const text = () => element.textContent ?? '';
    return { query, inputValue, type, click, respond, text };
  }

  describe('loading', () => {
    it('fills the form with the saved configuration', async () => {
      const { query, inputValue } = await render();

      expect(inputValue('#config-broker-url')).toBe('http://localhost:1026');
      expect(inputValue('#config-fiware-service')).toBe('openiot');
      expect(query<HTMLInputElement>('input[value="local"]')!.checked).toBeTrue();
    });

    it('shows an error with retry when the configuration cannot be loaded', () => {
      const fixture = TestBed.createComponent(ConfigComponent);
      httpMock.expectOne(`${BASE_URL}/config`).flush('boom', { status: 500, statusText: 'Error' });
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('app-error-state')).not.toBeNull();
    });
  });

  describe('going back', () => {
    it('offers a way back to the dashboard when a broker is already configured', async () => {
      const { click, query } = await render(savedResponse());

      expect(query('.config-back')!.textContent).toContain('Voltar ao painel');
      await click('.config-back');

      expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard');
    });

    it('does not offer to go back on the first setup, because the app needs a broker first', async () => {
      const { query } = await render();

      expect(query('.config-back')).toBeNull();
    });

    it('offers the way back right after the first configuration is saved', async () => {
      const { click, respond, query } = await render();

      await click('.config-submit');
      await respond(`${BASE_URL}/config`, savedResponse());

      expect(query('.config-back')).not.toBeNull();
    });
  });

  describe('choosing where the broker is', () => {
    it('shows the access key field only for a cloud broker and suggests https://', async () => {
      const { query, click, inputValue } = await render();
      expect(query('#config-api-key')).toBeNull();

      await click('input[value="cloud"]');

      expect(query('#config-api-key')).not.toBeNull();
      expect(inputValue('#config-broker-url')).toBe('https://');
    });

    it('goes back to the local Docker address when switching from cloud to local', async () => {
      const { type, click, inputValue } = await render();
      await click('input[value="cloud"]');
      await type('#config-broker-url', 'https://orion.example.com');

      await click('input[value="local"]');

      expect(inputValue('#config-broker-url')).toBe('http://localhost:1026');
    });

    it('says a key is already saved instead of showing it', async () => {
      const { query } = await render({
        ...LOADED,
        broker_kind: 'cloud',
        broker_url: 'https://orion.example.com',
        has_api_key: true,
      });

      const keyInput = query<HTMLInputElement>('#config-api-key')!;
      expect(keyInput.value).toBe('');
      expect(keyInput.placeholder).toContain('Chave salva');
    });
  });

  describe('field validation', () => {
    it('does not call the API and points to each invalid field', async () => {
      const { type, click, query, text } = await render();
      await type('#config-broker-url', 'localhost:1026');
      await type('#config-fiware-service-path', 'sem-barra');

      await click('.config-test');

      httpMock.expectNone(`${BASE_URL}/config/test`);
      expect(query('#config-broker-url')!.getAttribute('aria-invalid')).toBe('true');
      expect(text()).toContain('Use o formato http://endereço:porta');
      expect(text()).toContain('Comece com /');
      expect(document.activeElement?.id).toBe('config-broker-url');
    });

    it('explains the Fiware-ServicePath format next to the field, before any error', async () => {
      const { query } = await render();

      const hint = query<HTMLElement>('#config-fiware-service-path-hint')!;
      expect(hint.textContent).toContain('começando com /');
      expect(hint.textContent).toContain('/cidade/iluminacao');
      expect(query('#config-fiware-service-path')!.getAttribute('aria-describedby')).toBe(
        'config-fiware-service-path-hint'
      );
    });

    it('keeps the Fiware-ServicePath hint and adds the error when the value is invalid', async () => {
      const { type, click, query } = await render();
      await type('#config-fiware-service-path', 'sem-barra');

      await click('.config-test');

      httpMock.expectNone(`${BASE_URL}/config/test`);
      expect(query('#config-fiware-service-path')!.getAttribute('aria-describedby')).toBe(
        'config-fiware-service-path-hint config-fiware-service-path-error'
      );
    });

    it('clears the message as soon as the field is corrected', async () => {
      const { type, click, text } = await render();
      await type('#config-broker-url', '');
      await click('.config-test');
      expect(text()).toContain('Informe a URL do broker');

      await type('#config-broker-url', 'http://localhost:1026');

      expect(text()).not.toContain('Informe a URL do broker');
    });
  });

  describe('testing the connection before saving', () => {
    it('tests the typed values without saving them', async () => {
      const { click, respond, text } = await render();

      await click('.config-test');
      const request = await respond(`${BASE_URL}/config/test`, REACHABLE);

      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({
        broker_url: 'http://localhost:1026',
        fiware_service: 'openiot',
        fiware_service_path: '/',
        broker_kind: 'local',
        broker_api_key: null,
        ngsi_version: 'v2',
      });
      expect(text()).toContain('Conexão funcionando');
      expect(text()).toContain('2 tipo(s) de entidade');
    });

    it('explains a refused credential with the HTTP status', async () => {
      const { click, type, respond, text } = await render();
      await click('input[value="cloud"]');
      await type('#config-broker-url', 'https://orion.example.com');
      await type('#config-api-key', 'chave-errada');

      await click('.config-test');
      const request = await respond(`${BASE_URL}/config/test`, failure('unauthorized', 401));

      expect(request.request.body.broker_api_key).toBe('chave-errada');
      expect(text()).toContain('Credencial recusada pelo broker (HTTP 401)');
    });

    it('hides an old result once a value is changed', async () => {
      const { click, type, respond, text } = await render();
      await click('.config-test');
      await respond(`${BASE_URL}/config/test`, failure('unreachable'));
      expect(text()).toContain('Broker inacessível');

      await type('#config-broker-url', 'http://localhost:1027');

      expect(text()).not.toContain('Broker inacessível');
    });

    it('says when the auditor API itself could not run the test', async () => {
      const { click, respond, text } = await render();

      await click('.config-test');
      await respond(`${BASE_URL}/config/test`, 'down', 502);

      expect(text()).toContain('a API do auditor não respondeu');
    });
  });

  describe('saving', () => {
    it('saves when the connection works and lets the user continue', async () => {
      const { click, respond, text } = await render();

      await click('.config-submit');
      const request = await respond(`${BASE_URL}/config`, savedResponse());

      expect(request.request.method).toBe('PUT');
      expect(request.request.body.save_without_connection).toBeFalse();
      expect(text()).toContain('Configuração salva.');
      expect(text()).toContain('2 tipo(s) de entidade');
      await click('.config-continue');
      expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard');
    });

    it('does not save a configuration that fails the connection test without an explicit confirmation', async () => {
      const { click, respond, query, text } = await render();

      await click('.config-submit');
      await respond(
        `${BASE_URL}/config`,
        { detail: { message: 'falhou', connection: failure('unreachable') } },
        409
      );

      expect(text()).toContain('A configuração não foi salva');
      expect(text()).toContain('Broker inacessível');
      expect(query('.config-continue')).toBeNull();
      expect(query('.config-submit')).toBeNull();
    });

    it('saves anyway only after the user confirms, and warns that audits will fail', async () => {
      const { click, respond, text } = await render();
      await click('.config-submit');
      await respond(`${BASE_URL}/config`, { detail: { message: 'falhou', connection: failure('timeout') } }, 409);

      await click('.config-save-anyway');
      const request = await respond(`${BASE_URL}/config`, savedResponse({ connection: null }));

      expect(request.request.body.save_without_connection).toBeTrue();
      expect(text()).toContain('Configuração salva sem conexão confirmada');
    });

    it('returns to the form when the user chooses to fix the configuration', async () => {
      const { click, respond, query } = await render();
      await click('.config-submit');
      await respond(`${BASE_URL}/config`, { detail: { message: 'falhou', connection: failure('unreachable') } }, 409);

      await click('.config-fix');

      expect(query('.config-submit')).not.toBeNull();
      expect(document.activeElement?.id).toBe('config-broker-url');
    });

    it('shows a generic error when the API fails for another reason', async () => {
      const { click, respond, text } = await render();

      await click('.config-submit');
      await respond(`${BASE_URL}/config`, 'boom', 500);

      expect(text()).toContain('Não foi possível salvar a configuração');
    });

    it('updates the session tenant from the saved configuration without asking the API again', async () => {
      const { click, respond } = await render();
      const session = TestBed.inject(SessionService);
      session.session.set({ deployment_mode: 'selfhosted', tenant: null });

      await click('.config-submit');
      await respond(`${BASE_URL}/config`, savedResponse({ fiware_service: 'novo_tenant', fiware_service_path: '/x' }));

      httpMock.expectNone(`${BASE_URL}/session`);
      expect(session.session()).toEqual({
        deployment_mode: 'selfhosted',
        tenant: { fiware_service: 'novo_tenant', fiware_service_path: '/x' },
      });
    });
  });
});
