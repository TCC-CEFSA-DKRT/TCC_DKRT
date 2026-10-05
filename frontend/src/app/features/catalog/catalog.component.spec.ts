import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';

import { CatalogComponent } from './catalog.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

function flushSuccessfulStatus(httpMock: HttpTestingController) {
  httpMock.expectOne(`${BASE_URL}/catalog`).flush({
    last_synced_at: '2026-08-20T12:00:00Z',
    last_sync_successful: true,
    last_sync_error: null,
    models_count: 42,
  });
}

function expectModelsRequest(httpMock: HttpTestingController) {
  return httpMock.expectOne((r) => r.url === `${BASE_URL}/catalog/models`);
}

describe('CatalogComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CatalogComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('shows the last successful sync date, never omitting it', () => {
    const fixture = TestBed.createComponent(CatalogComponent);
    fixture.detectChanges();

    flushSuccessfulStatus(httpMock);
    fixture.detectChanges();
    // Depois de um sync bem-sucedido, a lista de modelos e' carregada
    // automaticamente -- sem flusha-la aqui, httpMock.verify() no
    // afterEach acusaria uma requisicao pendente.
    expectModelsRequest(httpMock).flush({ items: [], page: 1, page_size: 20, total: 0, has_next: false });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('20/08/2026');
    expect(text).toContain('42');
  });

  it('shows the local (last successful) catalog with an explicit warning on a failed sync attempt, never hiding the failure or serving stale data as current', () => {
    const fixture = TestBed.createComponent(CatalogComponent);
    fixture.detectChanges();

    httpMock.expectOne(`${BASE_URL}/catalog`).flush({
      last_synced_at: '2026-08-20T12:00:00Z',
      last_sync_successful: false,
      last_sync_error: 'Hugging Face Hub unreachable (403)',
      models_count: 42,
    });
    fixture.detectChanges();
    expectModelsRequest(httpMock).flush({ items: [], page: 1, page_size: 20, total: 0, has_next: false });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    // O aviso de falha é explícito...
    expect(text).toContain('falhou');
    expect(text).toContain('Hugging Face Hub unreachable (403)');
    // ...e o catálogo local (última sincronização boa) continua visível,
    // nunca escondido ou substituído por "sem dados".
    expect(text).toContain('20/08/2026');
    expect(text).toContain('42');
  });

  it('never fetches the models list before a successful sync has happened', () => {
    const fixture = TestBed.createComponent(CatalogComponent);
    fixture.detectChanges();

    httpMock.expectOne(`${BASE_URL}/catalog`).flush({
      last_synced_at: null,
      last_sync_successful: null,
      last_sync_error: null,
      models_count: null,
    });
    fixture.detectChanges();

    // Nao ha' requisicao pendente para /catalog/models -- httpMock.verify()
    // no afterEach garante isso (falharia se algo tivesse sido disparado).
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('não foi sincronizado');
  });

  describe('models list', () => {
    function setup(fixture: ReturnType<typeof TestBed.createComponent<CatalogComponent>>) {
      fixture.detectChanges();
      flushSuccessfulStatus(httpMock);
      fixture.detectChanges();
    }

    it('lists the subject and model name of every returned model', () => {
      const fixture = TestBed.createComponent(CatalogComponent);
      setup(fixture);

      expectModelsRequest(httpMock).flush({
        items: [
          { subject: 'dataModel.Streetlighting', model_name: 'Streetlight' },
          { subject: 'dataModel.Weather', model_name: 'WeatherObserved' },
        ],
        page: 1,
        page_size: 20,
        total: 2,
        has_next: false,
      });
      fixture.detectChanges();

      const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(text).toContain('dataModel.Streetlighting');
      expect(text).toContain('Streetlight');
      expect(text).toContain('dataModel.Weather');
      expect(text).toContain('WeatherObserved');
      expect(text).toContain('2 modelo(s) no total');
    });

    it('sends the search box and subject filter as query params on submit', () => {
      const fixture = TestBed.createComponent(CatalogComponent);
      setup(fixture);
      expectModelsRequest(httpMock).flush({ items: [], page: 1, page_size: 20, total: 0, has_next: false });
      fixture.detectChanges();

      const component = fixture.componentInstance as unknown as {
        modelSearchInput: string;
        modelSubjectInput: string;
        applyModelFilters(): void;
      };
      component.modelSearchInput = 'Street';
      component.modelSubjectInput = 'dataModel.Streetlighting';
      component.applyModelFilters();

      const request = expectModelsRequest(httpMock);
      expect(request.request.params.get('q')).toBe('Street');
      expect(request.request.params.get('subject')).toBe('dataModel.Streetlighting');
      request.flush({ items: [], page: 1, page_size: 20, total: 0, has_next: false });
    });

    it('fetches and shows a model schema when "Ver schema" is clicked, and hides it again on a second click', () => {
      const fixture = TestBed.createComponent(CatalogComponent);
      setup(fixture);
      expectModelsRequest(httpMock).flush({
        items: [{ subject: 'dataModel.Streetlighting', model_name: 'Streetlight' }],
        page: 1,
        page_size: 20,
        total: 1,
        has_next: false,
      });
      fixture.detectChanges();

      const toggleButton = (fixture.nativeElement as HTMLElement).querySelector(
        '.models-table__toggle'
      ) as HTMLButtonElement;
      toggleButton.click();
      fixture.detectChanges();

      const schemaRequest = httpMock.expectOne(
        (r) => r.url === `${BASE_URL}/catalog/models/Streetlight/schema`
      );
      expect(schemaRequest.request.params.get('subject')).toBe('dataModel.Streetlighting');
      schemaRequest.flush({
        subject: 'dataModel.Streetlighting',
        model_name: 'Streetlight',
        version: 'latest',
        schema_url: 'https://raw.githubusercontent.com/smart-data-models/dataModel.Streetlighting/master/Streetlight/schema.json',
        content: { type: 'object', title: 'Streetlight' },
        source: 'live',
        fetched_at: '2026-09-07T12:00:00Z',
      });
      fixture.detectChanges();

      let text = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(text).toContain('"title": "Streetlight"');
      expect(text).toContain('ao vivo');
      expect(text).toContain('Ocultar schema');

      toggleButton.click();
      fixture.detectChanges();
      text = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(text).not.toContain('"title": "Streetlight"');
      expect(text).toContain('Ver schema');
    });

    it('shows an error message, not a blank panel, when the schema request fails', () => {
      const fixture = TestBed.createComponent(CatalogComponent);
      setup(fixture);
      expectModelsRequest(httpMock).flush({
        items: [{ subject: 'dataModel.Streetlighting', model_name: 'Streetlight' }],
        page: 1,
        page_size: 20,
        total: 1,
        has_next: false,
      });
      fixture.detectChanges();

      const toggleButton = (fixture.nativeElement as HTMLElement).querySelector(
        '.models-table__toggle'
      ) as HTMLButtonElement;
      toggleButton.click();
      fixture.detectChanges();

      httpMock
        .expectOne((r) => r.url === `${BASE_URL}/catalog/models/Streetlight/schema`)
        .flush({ detail: 'sem cache e sem rede' }, { status: 404, statusText: 'Not Found' });
      fixture.detectChanges();

      const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(text).toContain('sem cache e sem rede');
    });
  });
});
