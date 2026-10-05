import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';

import { DashboardComponent } from './dashboard.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';
import { AuditRunSummaryResponse, PageResponse } from '../../shared/models/audit.models';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

function makeSummaryView(overrides: Partial<AuditRunSummaryResponse> = {}): AuditRunSummaryResponse {
  return {
    id: 'run-1',
    entity_type: 'Streetlight',
    status: 'completed',
    summary: {
      total_entities: 10,
      conformant_count: 6,
      non_conformant_count: 3,
      partial_count: 1,
      no_model_count: 0,
      schema_unavailable_count: 0,
    },
    started_at: '2026-09-01T10:00:00Z',
    finished_at: '2026-09-01T10:05:00Z',
    broker_url: 'http://orion:1026',
    total_entities_discovered: 10,
    failure_reason: null,
    ...overrides,
  };
}

describe('DashboardComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('shows the empty state when the tenant has no runs yet', () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const req = httpMock.expectOne((r) => r.url === `${BASE_URL}/audits`);
    req.flush({ items: [], page: 1, page_size: 200, total: 0, has_next: false } as PageResponse<
      AuditRunSummaryResponse
    >);
    fixture.detectChanges();

    expect((fixture.componentInstance as any).state()).toBe('empty');
  });

  it('aggregates category totals as an exact sum of RunSummary counts, never a divergent recompute', () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const runA = makeSummaryView({
      id: 'a',
      entity_type: 'Streetlight',
      summary: {
        total_entities: 5,
        conformant_count: 3,
        non_conformant_count: 2,
        partial_count: 0,
        no_model_count: 0,
        schema_unavailable_count: 0,
      },
    });
    const runB = makeSummaryView({
      id: 'b',
      entity_type: 'Streetlight',
      summary: {
        total_entities: 5,
        conformant_count: 1,
        non_conformant_count: 1,
        partial_count: 3,
        no_model_count: 0,
        schema_unavailable_count: 0,
      },
    });

    const req = httpMock.expectOne((r) => r.url === `${BASE_URL}/audits`);
    req.flush({ items: [runA, runB], page: 1, page_size: 200, total: 2, has_next: false });

    // Dashboard immediately fetches the time series for the first entity_type found.
    httpMock
      .expectOne((r) => r.url === `${BASE_URL}/audits/summary-over-time`)
      .flush([]);
    fixture.detectChanges();

    const component = fixture.componentInstance as any;
    expect(component.state()).toBe('loaded');
    const aggregates = component.categoryAggregates();
    expect(aggregates.length).toBe(1);
    expect(aggregates[0].summary.total_entities).toBe(10);
    expect(aggregates[0].summary.conformant_count).toBe(4);
    expect(aggregates[0].summary.non_conformant_count).toBe(3);
    expect(aggregates[0].summary.partial_count).toBe(3);
  });

  it('shows an explicit error state with retry when the summary API is unavailable, never an infinite loading', () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const req = httpMock.expectOne((r) => r.url === `${BASE_URL}/audits`);
    req.error(new ProgressEvent('network error'));
    fixture.detectChanges();

    expect((fixture.componentInstance as any).state()).toBe('error');
  });
});
