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
import { AuditRunSummaryResponse } from '../../shared/models/audit.models';

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
});
