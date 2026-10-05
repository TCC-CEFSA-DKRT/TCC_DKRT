import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { NaturalLanguageComponent } from './natural-language.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

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

  it('never calls POST /audits from interpret() alone — only after an explicit confirm click', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'audite os sensores de qualidade do ar';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      entity_type: 'AirQualityObserved',
      entity_id: null,
      confidence: 0.92,
      raw_command: 'audite os sensores de qualidade do ar',
    });
    fixture.detectChanges();

    // Nenhuma requisição POST /audits deve ter sido feita ainda.
    httpMock.expectNone(`${BASE_URL}/audits`);
    expect(component.confirmState()).toBe('idle');

    // Só dispara POST /audits com o clique explícito de confirmação.
    component.onConfirmClick();
    const createReq = httpMock.expectOne(`${BASE_URL}/audits`);
    expect(createReq.request.method).toBe('POST');
    createReq.flush({ run_id: 'run-1', status: 'queued' });
    fixture.detectChanges();

    expect(component.confirmState()).toBe('submitted');
  });

  it('links to the report for the run just created, so the user can check on it later', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'audite os sensores de qualidade do ar';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      entity_type: 'AirQualityObserved',
      entity_id: null,
      confidence: 0.92,
      raw_command: 'audite os sensores de qualidade do ar',
    });
    fixture.detectChanges();

    component.onConfirmClick();
    httpMock.expectOne(`${BASE_URL}/audits`).flush({ run_id: 'run-1', status: 'queued' });
    fixture.detectChanges();

    const link = (fixture.nativeElement as HTMLElement).querySelector(
      '.status-text--success a'
    ) as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link!.getAttribute('href')).toBe('/audit-runs/run-1');
  });

  it('offers no confirmation button for an empty/low-confidence interpretation', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'faz uma coisa ai';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      entity_type: null,
      entity_id: null,
      confidence: 0.1,
      raw_command: 'faz uma coisa ai',
    });
    fixture.detectChanges();

    expect(component.understoodEnough()).toBe(false);
    const confirmButton = (fixture.nativeElement as HTMLElement).querySelector(
      '.confirm-button'
    );
    expect(confirmButton).toBeNull();

    // Mesmo que alguém tente chamar onConfirmClick() diretamente (ex.: bug
    // de outro lugar do código), o guard interno nunca deixa passar.
    component.onConfirmClick();
    httpMock.expectNone(`${BASE_URL}/audits`);
  });

  it('uses the edited interpretation, not the original, when the user confirms', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'audite os postes';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      entity_type: 'StreetLightWrongGuess',
      entity_id: null,
      confidence: 0.7,
      raw_command: 'audite os postes',
    });
    fixture.detectChanges();

    // Usuário corrige o tipo sugerido antes de confirmar.
    component.editableEntityType = 'Streetlight';
    component.onConfirmClick();

    const createReq = httpMock.expectOne(`${BASE_URL}/audits`);
    expect(createReq.request.body).toEqual({ entity_type: 'Streetlight', entity_id: null });
    createReq.flush({ run_id: 'run-2', status: 'queued' });
  });

  it('shows the entity types discovered in the broker for a discovery question', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'quais entidades existem?';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      intent: 'discovery',
      entity_type: null,
      entity_id: null,
      confidence: 0.9,
      raw_command: 'quais entidades existem?',
      discovered_types: ['Streetlight', 'AirQualityObserved'],
      broker_reachable: true,
    });
    fixture.detectChanges();

    const nativeElement = fixture.nativeElement as HTMLElement;
    const types = Array.from(nativeElement.querySelectorAll('.discovery-panel__type')).map(
      (element) => element.textContent?.trim()
    );
    expect(types).toEqual(['Streetlight', 'AirQualityObserved']);
    expect(nativeElement.querySelector('.interpretation-panel--low-confidence')).toBeNull();
  });

  it('does not offer audit confirmation for a discovery result', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'quais entidades existem?';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      intent: 'discovery',
      entity_type: null,
      entity_id: null,
      confidence: 0.9,
      raw_command: 'quais entidades existem?',
      discovered_types: ['Streetlight', 'AirQualityObserved'],
      broker_reachable: true,
    });
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('.confirm-button')).toBeNull();
    expect(component.understoodEnough()).toBe(false);

    component.onConfirmClick();
    httpMock.expectNone(`${BASE_URL}/audits`);
  });

  it('never offers audit confirmation for a discovery result even if a type came back', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'quais entidades existem?';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
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
    expect((fixture.nativeElement as HTMLElement).querySelector('.confirm-button')).toBeNull();

    component.onConfirmClick();
    httpMock.expectNone(`${BASE_URL}/audits`);
  });

  it('warns when the broker is unreachable for a discovery question', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'quais entidades existem?';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      intent: 'discovery',
      entity_type: null,
      entity_id: null,
      confidence: 0.9,
      raw_command: 'quais entidades existem?',
      discovered_types: [],
      broker_reachable: false,
    });
    fixture.detectChanges();

    const nativeElement = fixture.nativeElement as HTMLElement;
    expect(nativeElement.querySelector('.discovery-panel__warning')).not.toBeNull();
    expect(nativeElement.querySelectorAll('.discovery-panel__type').length).toBe(0);
    expect(nativeElement.querySelector('.confirm-button')).toBeNull();
  });

  it('says the broker has no entity types when discovery returns an empty list', () => {
    const fixture = TestBed.createComponent(NaturalLanguageComponent);
    const component = fixture.componentInstance as any;
    component.commandText = 'quais entidades existem?';
    component.onInterpret();

    httpMock.expectOne(`${BASE_URL}/audits/interpret`).flush({
      intent: 'discovery',
      entity_type: null,
      entity_id: null,
      confidence: 0.9,
      raw_command: 'quais entidades existem?',
      discovered_types: [],
      broker_reachable: true,
    });
    fixture.detectChanges();

    const nativeElement = fixture.nativeElement as HTMLElement;
    expect(nativeElement.querySelector('.discovery-panel__empty')).not.toBeNull();
    expect(nativeElement.querySelector('.discovery-panel__warning')).toBeNull();
  });
});
