import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { convertToParamMap } from '@angular/router';

import { AuditRunsComponent } from './audit-runs.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';
import { AuditRunSummaryResponse } from '../../shared/interfaces/audit.interface';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

function makeRun(overrides: Partial<AuditRunSummaryResponse> = {}): AuditRunSummaryResponse {
  return {
    id: 'run-1',
    entity_type: 'Streetlight',
    status: 'running',
    summary: {
      total_entities: 0,
      conformant_count: 0,
      non_conformant_count: 0,
      partial_count: 0,
      no_model_count: 0,
      schema_unavailable_count: 0,
    },
    started_at: '2026-09-01T10:00:00Z',
    finished_at: null,
    broker_url: 'http://orion:1026',
    total_entities_discovered: null,
    failure_reason: null,
    ...overrides,
  };
}

describe('AuditRunsComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AuditRunsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap({}) } },
        },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it("updates a running run's progress via polling without a full page reload", fakeAsync(() => {
    const fixture = TestBed.createComponent(AuditRunsComponent);
    fixture.detectChanges();

    httpMock
      .expectOne((r) => r.url === `${BASE_URL}/audits`)
      .flush({ items: [makeRun()], page: 1, page_size: 20, total: 1, has_next: false });
    fixture.detectChanges();

    tick(5000);
    httpMock
      .expectOne(`${BASE_URL}/audits/run-1/progress`)
      .flush({ status: 'running', processed: 3, total: 10 });
    fixture.detectChanges();

    const component = fixture.componentInstance as any;
    expect(component.progressByRunId()['run-1']).toEqual({
      status: 'running',
      processed: 3,
      total: 10,
    });

    tick(5000);
    httpMock
      .expectOne(`${BASE_URL}/audits/run-1/progress`)
      .flush({ status: 'running', processed: 7, total: 10 });
    fixture.detectChanges();

    // Destrói o componente antes do fim do teste: dispara
    // takeUntilDestroyed() e cancela o polling, evitando que o interval
    // ainda pendente dispare mais uma requisição depois que esta função
    // fakeAsync já retornou (fora da zona de tempo virtual).
    fixture.destroy();
  }));

  it('shows "processando…" without an invented denominator while total is null', () => {
    const fixture = TestBed.createComponent(AuditRunsComponent);
    fixture.detectChanges();

    httpMock
      .expectOne((r) => r.url === `${BASE_URL}/audits`)
      .flush({ items: [makeRun()], page: 1, page_size: 20, total: 1, has_next: false });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('processando…');
    expect(text).not.toContain('undefined');
    expect(text).not.toMatch(/0\/0|\?\/0/);

    fixture.destroy();
  });

  it('reflects combined filters (type + status) into the URL query params', () => {
    const fixture = TestBed.createComponent(AuditRunsComponent);
    fixture.detectChanges();
    httpMock
      .expectOne((r) => r.url === `${BASE_URL}/audits`)
      .flush({ items: [], page: 1, page_size: 20, total: 0, has_next: false });
    fixture.detectChanges();

    const router = TestBed.inject(Router);
    const navigateSpy = spyOn(router, 'navigate');

    (fixture.componentInstance as any).applyFilters({
      entity_type: 'AirQualityObserved',
      status: 'partial',
      page: 1,
      page_size: 20,
    });

    expect(navigateSpy).toHaveBeenCalledWith(
      [],
      jasmine.objectContaining({
        queryParams: jasmine.objectContaining({
          entity_type: 'AirQualityObserved',
          status: 'partial',
        }),
      })
    );

    httpMock.expectOne((r) => r.url === `${BASE_URL}/audits`).flush({
      items: [],
      page: 1,
      page_size: 20,
      total: 0,
      has_next: false,
    });

    fixture.destroy();
  });

  describe('filters', () => {
    function renderWithNoRuns() {
      const fixture = TestBed.createComponent(AuditRunsComponent);
      fixture.detectChanges();
      httpMock
        .expectOne((r) => r.url === `${BASE_URL}/audits`)
        .flush({ items: [], page: 1, page_size: 20, total: 0, has_next: false });
      fixture.detectChanges();
      const element: HTMLElement = fixture.nativeElement;
      const typeInput = element.querySelector<HTMLInputElement>('input[name="entity_type"]')!;
      const focusTypeInput = () => {
        typeInput.dispatchEvent(new Event('focus'));
        fixture.detectChanges();
      };
      const suggestions = () =>
        Array.from(element.querySelectorAll<HTMLOptionElement>('#audit-runs-entity-types option')).map(
          (option) => option.value
        );
      return { fixture, element, typeInput, focusTypeInput, suggestions };
    }

    it('lists every run status in Portuguese, including runs that found no entities', () => {
      const { fixture, element } = renderWithNoRuns();

      const labels = Array.from(element.querySelectorAll<HTMLOptionElement>('select[name="status"] option')).map(
        (option) => option.textContent?.trim()
      );
      const values = Array.from(element.querySelectorAll<HTMLOptionElement>('select[name="status"] option')).map(
        (option) => option.value
      );

      expect(labels).toEqual([
        'Todos os status',
        'Na fila',
        'Em execução',
        'Concluído',
        'Parcial',
        'Falhou',
        'Nenhuma entidade encontrada',
      ]);
      expect(values).toContain('no_entities_found');
      fixture.destroy();
    });

    it('gives the type and status filters a name that screen readers can announce', () => {
      const { fixture, element, typeInput } = renderWithNoRuns();

      expect(typeInput.getAttribute('aria-label')).toBe('Filtrar por tipo de entidade');
      expect(element.querySelector('select[name="status"]')!.getAttribute('aria-label')).toBe('Filtrar por status');
      fixture.destroy();
    });

    it('suggests the entity types that exist in the broker once the type filter gets focus, asking only once', () => {
      const { fixture, typeInput, focusTypeInput, suggestions } = renderWithNoRuns();
      httpMock.expectNone(`${BASE_URL}/entity-types`);

      focusTypeInput();
      httpMock
        .expectOne(`${BASE_URL}/entity-types`)
        .flush({ types: ['Streetlight', 'AirQualityObserved'], broker_reachable: true });
      fixture.detectChanges();
      focusTypeInput();

      httpMock.expectNone(`${BASE_URL}/entity-types`);
      expect(typeInput.getAttribute('list')).toBe('audit-runs-entity-types');
      expect(suggestions()).toEqual(['Streetlight', 'AirQualityObserved']);
      fixture.destroy();
    });

    it('keeps the type filter as free text and asks again on the next focus when the suggestions fail', () => {
      const { fixture, typeInput, focusTypeInput, suggestions } = renderWithNoRuns();

      focusTypeInput();
      httpMock
        .expectOne(`${BASE_URL}/entity-types`)
        .flush('erro', { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(suggestions()).toEqual([]);
      expect(typeInput.disabled).toBeFalse();

      focusTypeInput();
      httpMock.expectOne(`${BASE_URL}/entity-types`).flush({ types: ['Streetlight'], broker_reachable: true });
      fixture.detectChanges();

      expect(suggestions()).toEqual(['Streetlight']);
      fixture.destroy();
    });
  });
});
