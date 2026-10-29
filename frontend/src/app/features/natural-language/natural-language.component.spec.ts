import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { NaturalLanguageComponent } from './natural-language.component';
import { INTERPRET_TIMEOUT_MS } from './natural-language-api.service';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;
const INTERPRET_URL = `${BASE_URL}/audits/interpret`;
const AUDITS_URL = `${BASE_URL}/audits`;

/** Palavras que denunciariam um erro técnico vazando para a tela. */
const TECHNICAL_ERROR_MARKERS = ['Http failure', 'HttpErrorResponse', 'undefined', 'null', 'stack'];

describe('NaturalLanguageComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NaturalLanguageComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function setup(command: string) {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    const element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
    component.commandText.set(command);
    component.onInterpret();
    fixture.detectChanges();
    return { fixture, component, element };
  }

  function expectNoTechnicalError(text: string | null | undefined) {
    for (const marker of TECHNICAL_ERROR_MARKERS) {
      expect(text ?? '').not.toContain(marker);
    }
  }

  describe('explicit confirmation (critério de aceite)', () => {
    it('never calls POST /audits from interpret() alone — only after an explicit confirm click', () => {
      const { fixture, component } = setup('audite os sensores de qualidade do ar');

      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'AirQualityObserved',
        entity_id: null,
        confidence: 0.92,
        raw_command: 'audite os sensores de qualidade do ar',
      });
      fixture.detectChanges();

      // Nenhuma requisição POST /audits deve ter sido feita ainda.
      httpMock.expectNone(AUDITS_URL);
      expect(component.confirmState()).toBe('idle');

      // Só dispara POST /audits com o clique explícito de confirmação.
      component.onConfirmClick();
      const createReq = httpMock.expectOne(AUDITS_URL);
      expect(createReq.request.method).toBe('POST');
      createReq.flush({ run_id: 'run-1', status: 'queued' });
      fixture.detectChanges();

      expect(component.confirmState()).toBe('submitted');
    });

    it('starts the audit only when the confirm button itself is clicked in the page', () => {
      const { fixture, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'audit',
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.9,
        raw_command: 'audite os postes',
        discovered_types: null,
        broker_reachable: null,
      });
      fixture.detectChanges();
      httpMock.expectNone(AUDITS_URL);

      (element.querySelector('.confirm-button') as HTMLButtonElement).click();

      const createReq = httpMock.expectOne(AUDITS_URL);
      expect(createReq.request.body).toEqual({ entity_type: 'Streetlight', entity_id: null });
      createReq.flush({ run_id: 'run-9', status: 'queued' });
    });

    it('links to the report for the run just created, so the user can check on it later', () => {
      const { fixture, component, element } = setup('audite os sensores de qualidade do ar');

      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'AirQualityObserved',
        entity_id: null,
        confidence: 0.92,
        raw_command: 'audite os sensores de qualidade do ar',
      });
      fixture.detectChanges();

      component.onConfirmClick();
      httpMock.expectOne(AUDITS_URL).flush({ run_id: 'run-1', status: 'queued' });
      fixture.detectChanges();

      const link = element.querySelector('.status-text--success a') as HTMLAnchorElement | null;
      expect(link).not.toBeNull();
      expect(link!.getAttribute('href')).toBe('/audit-runs/run-1');
    });

    it('uses the edited interpretation, not the original, when the user confirms', () => {
      const { fixture, component } = setup('audite os postes');

      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'StreetLightWrongGuess',
        entity_id: null,
        confidence: 0.7,
        raw_command: 'audite os postes',
      });
      fixture.detectChanges();

      // Usuário corrige o tipo sugerido antes de confirmar.
      component.editableEntityType.set('Streetlight');
      component.onConfirmClick();

      const createReq = httpMock.expectOne(AUDITS_URL);
      expect(createReq.request.body).toEqual({ entity_type: 'Streetlight', entity_id: null });
      createReq.flush({ run_id: 'run-2', status: 'queued' });
    });

    it('does not allow confirming when the user clears the entity type', () => {
      const { fixture, component, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.9,
        raw_command: 'audite os postes',
      });
      component.editableEntityType.set('   ');
      fixture.detectChanges();

      const button = element.querySelector('.confirm-button') as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      expect(element.querySelector('.field-hint')).not.toBeNull();

      component.onConfirmClick();
      httpMock.expectNone(AUDITS_URL);
    });

    it('sends a single POST /audits even if confirm is clicked twice', () => {
      const { fixture, component, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.9,
        raw_command: 'audite os postes',
      });
      fixture.detectChanges();

      component.onConfirmClick();
      component.onConfirmClick();
      fixture.detectChanges();

      const button = element.querySelector('.confirm-button') as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      expect(button.textContent).toContain('Iniciando auditoria');

      const requests = httpMock.match(AUDITS_URL);
      expect(requests.length).toBe(1);
      requests[0].flush({ run_id: 'run-3', status: 'queued' });
      fixture.detectChanges();

      component.onConfirmClick();
      httpMock.expectNone(AUDITS_URL);
    });
  });

  describe('shows how the request was interpreted', () => {
    it('shows intent, extracted parameters and confidence before anything runs', () => {
      const { fixture, element } = setup('verifique a entidade urn:ngsi-ld:Streetlight:001');
      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'audit',
        entity_type: 'Streetlight',
        entity_id: 'urn:ngsi-ld:Streetlight:001',
        confidence: 0.92,
        raw_command: 'verifique a entidade urn:ngsi-ld:Streetlight:001',
        discovered_types: null,
        broker_reachable: null,
      });
      fixture.detectChanges();

      const panel = element.querySelector('.understanding-panel');
      expect(panel).not.toBeNull();
      expect(element.querySelector('.understanding-list__intent')?.textContent).toContain(
        'Auditar entidades'
      );
      const params = Array.from(element.querySelectorAll('.understanding-list__param')).map((e) =>
        e.textContent?.trim()
      );
      expect(params).toEqual(['Streetlight', 'urn:ngsi-ld:Streetlight:001']);
      const badge = element.querySelector('.confidence-badge');
      expect(badge?.textContent).toContain('92%');
      expect(badge?.textContent).toContain('alta');
      expect(badge?.classList).toContain('confidence-badge--alta');
      httpMock.expectNone(AUDITS_URL);
    });

    it('labels a medium confidence interpretation as "média"', () => {
      const { fixture, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.6,
        raw_command: 'audite os postes',
      });
      fixture.detectChanges();

      expect(element.querySelector('.confidence-badge')?.textContent).toContain('60% · média');
    });
  });

  describe('loading state', () => {
    it('shows a loading message and blocks a second submission while interpreting', () => {
      const { fixture, component, element } = setup('audite os postes');

      expect(element.querySelector('.status-text--loading')).not.toBeNull();
      const submit = element.querySelector('.command-form__submit') as HTMLButtonElement;
      expect(submit.disabled).toBe(true);
      expect(submit.textContent).toContain('Interpretando');

      component.onInterpret();
      const requests = httpMock.match(INTERPRET_URL);
      expect(requests.length).toBe(1);
      requests[0].flush({
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.9,
        raw_command: 'audite os postes',
      });
      fixture.detectChanges();

      expect(element.querySelector('.status-text--loading')).toBeNull();
    });

    it('does not send an empty command', () => {
      const fixture = TestBed.createComponent(NaturalLanguageComponent);
      const component = fixture.componentInstance as any;
      fixture.detectChanges();

      component.commandText.set('   ');
      component.onInterpret();

      httpMock.expectNone(INTERPRET_URL);
      expect(component.interpretState()).toBe('idle');
    });
  });

  describe('ambiguous requests → clarification question', () => {
    it('asks a clarification question and offers the broker types as suggestions', () => {
      const { fixture, component, element } = setup('audite os sensores');
      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'clarify',
        entity_type: null,
        entity_id: null,
        confidence: 0.4,
        raw_command: 'audite os sensores',
        discovered_types: ['AirQualityObserved', 'WeatherObserved'],
        broker_reachable: true,
        clarification_question: 'Quais sensores você quer auditar?',
        interpreter_available: true,
      });
      fixture.detectChanges();

      expect(element.querySelector('.clarify-panel__question')?.textContent).toContain(
        'Quais sensores você quer auditar?'
      );
      const chips = Array.from(element.querySelectorAll('.suggestion-chip')).map((e) =>
        e.textContent?.trim()
      );
      expect(chips).toEqual(['AirQualityObserved', 'WeatherObserved']);
      expect(element.querySelector('.confirm-button')).toBeNull();
      expect(component.understoodEnough()).toBe(false);

      component.onConfirmClick();
      httpMock.expectNone(AUDITS_URL);
    });

    it('choosing a suggestion opens the review panel but still requires the confirm click', () => {
      const { fixture, element } = setup('audite os sensores');
      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'clarify',
        entity_type: null,
        entity_id: null,
        confidence: 0.4,
        raw_command: 'audite os sensores',
        discovered_types: ['AirQualityObserved', 'WeatherObserved'],
        broker_reachable: true,
        clarification_question: 'Quais sensores você quer auditar?',
        interpreter_available: true,
      });
      fixture.detectChanges();

      (element.querySelectorAll('.suggestion-chip')[1] as HTMLButtonElement).click();
      fixture.detectChanges();

      // Escolher a sugestão NÃO executa nada.
      httpMock.expectNone(AUDITS_URL);
      expect(element.querySelector('.clarify-panel')).toBeNull();
      const typeInput = element.querySelector(
        '.interpretation-field__input[name="entityType"]'
      ) as HTMLInputElement;
      expect(typeInput).not.toBeNull();
      expect(element.querySelector('.understanding-list__intent')?.textContent).toContain(
        'tipo escolhido por você'
      );

      (element.querySelector('.confirm-button') as HTMLButtonElement).click();
      const createReq = httpMock.expectOne(AUDITS_URL);
      expect(createReq.request.body).toEqual({ entity_type: 'WeatherObserved', entity_id: null });
      createReq.flush({ run_id: 'run-4', status: 'queued' });
    });

    it('offers no confirmation button for an empty/low-confidence interpretation', () => {
      const { fixture, component, element } = setup('faz uma coisa ai');

      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: null,
        entity_id: null,
        confidence: 0.1,
        raw_command: 'faz uma coisa ai',
      });
      fixture.detectChanges();

      expect(component.understoodEnough()).toBe(false);
      expect(element.querySelector('.confirm-button')).toBeNull();
      // Mesmo sem `clarification_question`, a tela faz uma pergunta padrão.
      expect(element.querySelector('.clarify-panel__question')?.textContent?.trim()).toBeTruthy();

      // Mesmo que alguém tente chamar onConfirmClick() diretamente (ex.: bug
      // de outro lugar do código), o guard interno nunca deixa passar.
      component.onConfirmClick();
      httpMock.expectNone(AUDITS_URL);
    });

    it('warns when the broker could not be reached to suggest types', () => {
      const { fixture, element } = setup('audite tudo');
      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'clarify',
        entity_type: null,
        entity_id: null,
        confidence: 0.2,
        raw_command: 'audite tudo',
        discovered_types: [],
        broker_reachable: false,
        clarification_question: 'O que você quer auditar?',
        interpreter_available: true,
      });
      fixture.detectChanges();

      expect(element.querySelector('.clarify-panel .discovery-panel__warning')).not.toBeNull();
      expect(element.querySelectorAll('.suggestion-chip').length).toBe(0);
    });
  });

  describe('requests outside the FIWARE domain', () => {
    it('explains the request is out of scope, executes nothing and offers examples', () => {
      const { fixture, component, element } = setup('qual a capital da França?');
      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'out_of_scope',
        entity_type: null,
        entity_id: null,
        confidence: 0.95,
        raw_command: 'qual a capital da França?',
        discovered_types: null,
        broker_reachable: null,
        clarification_question: null,
        interpreter_available: true,
      });
      fixture.detectChanges();

      const panel = element.querySelector('.out-of-scope-panel');
      expect(panel).not.toBeNull();
      expect(panel?.textContent).toContain('Nada foi executado');
      expect(element.querySelector('.confirm-button')).toBeNull();
      expect(component.understoodEnough()).toBe(false);

      // Clicar num exemplo só preenche a caixa de texto.
      (element.querySelector('.example-chip') as HTMLButtonElement).click();
      fixture.detectChanges();
      expect(component.commandText()).toBe('audite os sensores de qualidade do ar');
      httpMock.expectNone(INTERPRET_URL);

      component.onConfirmClick();
      httpMock.expectNone(AUDITS_URL);
    });
  });

  describe('error states without technical details', () => {
    it('shows a friendly message when the language model is unavailable', () => {
      const { fixture, component, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'audit',
        entity_type: null,
        entity_id: null,
        confidence: 0,
        raw_command: 'audite os postes',
        discovered_types: null,
        broker_reachable: null,
        clarification_question: null,
        interpreter_available: false,
      });
      fixture.detectChanges();

      const message = element.querySelector('.error-state__message')?.textContent;
      expect(message).toContain('modelo de linguagem não respondeu');
      expect(element.querySelector('.understanding-panel')).toBeNull();
      expect(element.querySelector('.confirm-button')).toBeNull();
      expect(component.understoodEnough()).toBe(false);

      // "Tentar novamente" interpreta de novo.
      (element.querySelector('.error-state__retry') as HTMLButtonElement).click();
      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.9,
        raw_command: 'audite os postes',
      });
      fixture.detectChanges();
      expect(element.querySelector('.confirm-button')).not.toBeNull();
    });

    it('turns an HTTP 500 into a clear message, never a technical error', () => {
      const { fixture, element } = setup('audite os postes');
      httpMock
        .expectOne(INTERPRET_URL)
        .flush({ detail: 'Traceback (most recent call last)...' }, {
          status: 500,
          statusText: 'Internal Server Error',
        });
      fixture.detectChanges();

      const message = element.querySelector('.error-state__message')?.textContent;
      expect(message).toContain('indisponível');
      expect(message).not.toContain('Traceback');
      expect(message).not.toContain('500');
      expectNoTechnicalError(message);
    });

    it('explains when the API cannot be reached at all', () => {
      const { fixture, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL).error(new ProgressEvent('error'), { status: 0 });
      fixture.detectChanges();

      const message = element.querySelector('.error-state__message')?.textContent;
      expect(message).toContain('Não foi possível conectar');
      expectNoTechnicalError(message);
    });

    it('explains an invalid command (422) in plain words', () => {
      const { fixture, element } = setup('audite os postes');
      httpMock
        .expectOne(INTERPRET_URL)
        .flush({ detail: [{ loc: ['body', 'command_text'] }] }, {
          status: 422,
          statusText: 'Unprocessable Entity',
        });
      fixture.detectChanges();

      const message = element.querySelector('.error-state__message')?.textContent;
      expect(message).toContain('500 caracteres');
      expect(message).not.toContain('command_text');
    });

    it('stops waiting after the timeout and shows a clear message', fakeAsync(() => {
      const { fixture, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL);

      tick(INTERPRET_TIMEOUT_MS);
      fixture.detectChanges();

      expect(element.querySelector('.status-text--loading')).toBeNull();
      expect(element.querySelector('.error-state__message')?.textContent).toContain('demorou');
    }));

    it('shows a clear message when starting the audit fails, and allows retrying', () => {
      const { fixture, component, element } = setup('audite os postes');
      httpMock.expectOne(INTERPRET_URL).flush({
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.9,
        raw_command: 'audite os postes',
      });
      fixture.detectChanges();

      component.onConfirmClick();
      httpMock
        .expectOne(AUDITS_URL)
        .flush('boom', { status: 503, statusText: 'Service Unavailable' });
      fixture.detectChanges();

      const message = element.querySelector('.confirm-panel .error-state__message')?.textContent;
      expect(message).toContain('Não foi possível iniciar a auditoria');
      expect(message).not.toContain('boom');

      (element.querySelector('.confirm-panel .error-state__retry') as HTMLButtonElement).click();
      httpMock.expectOne(AUDITS_URL).flush({ run_id: 'run-5', status: 'queued' });
      fixture.detectChanges();
      expect(component.confirmState()).toBe('submitted');
    });
  });

  describe('discovery questions', () => {
    it('shows the entity types discovered in the broker for a discovery question', () => {
      const { fixture, element } = setup('quais entidades existem?');

      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'discovery',
        entity_type: null,
        entity_id: null,
        confidence: 0.9,
        raw_command: 'quais entidades existem?',
        discovered_types: ['Streetlight', 'AirQualityObserved'],
        broker_reachable: true,
      });
      fixture.detectChanges();

      const types = Array.from(element.querySelectorAll('.discovery-panel__type')).map((e) =>
        e.textContent?.trim()
      );
      expect(types).toEqual(['Streetlight', 'AirQualityObserved']);
      expect(element.querySelector('.clarify-panel')).toBeNull();
    });

    it('does not offer audit confirmation for a discovery result', () => {
      const { fixture, component, element } = setup('quais entidades existem?');

      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'discovery',
        entity_type: null,
        entity_id: null,
        confidence: 0.9,
        raw_command: 'quais entidades existem?',
        discovered_types: ['Streetlight', 'AirQualityObserved'],
        broker_reachable: true,
      });
      fixture.detectChanges();

      expect(element.querySelector('.confirm-button')).toBeNull();
      expect(component.understoodEnough()).toBe(false);

      component.onConfirmClick();
      httpMock.expectNone(AUDITS_URL);
    });

    it('never offers audit confirmation for a discovery result even if a type came back', () => {
      const { fixture, component, element } = setup('quais entidades existem?');

      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'discovery',
        entity_type: 'Streetlight',
        entity_id: null,
        confidence: 0.9,
        raw_command: 'quais entidades existem?',
        discovered_types: ['Streetlight'],
        broker_reachable: true,
      });
      fixture.detectChanges();

      expect(component.understoodEnough()).toBe(false);
      expect(element.querySelector('.confirm-button')).toBeNull();

      component.onConfirmClick();
      httpMock.expectNone(AUDITS_URL);
    });

    it('warns when the broker is unreachable for a discovery question', () => {
      const { fixture, element } = setup('quais entidades existem?');

      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'discovery',
        entity_type: null,
        entity_id: null,
        confidence: 0.9,
        raw_command: 'quais entidades existem?',
        discovered_types: [],
        broker_reachable: false,
      });
      fixture.detectChanges();

      expect(element.querySelector('.discovery-panel__warning')).not.toBeNull();
      expect(element.querySelectorAll('.discovery-panel__type').length).toBe(0);
      expect(element.querySelector('.confirm-button')).toBeNull();
    });

    it('says the broker has no entity types when discovery returns an empty list', () => {
      const { fixture, element } = setup('quais entidades existem?');

      httpMock.expectOne(INTERPRET_URL).flush({
        intent: 'discovery',
        entity_type: null,
        entity_id: null,
        confidence: 0.9,
        raw_command: 'quais entidades existem?',
        discovered_types: [],
        broker_reachable: true,
      });
      fixture.detectChanges();

      expect(element.querySelector('.discovery-panel__empty')).not.toBeNull();
      expect(element.querySelector('.discovery-panel__warning')).toBeNull();
    });
  });
});
