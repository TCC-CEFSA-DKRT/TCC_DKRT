import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap } from '@angular/router';

import { ReportDetailComponent } from './report-detail.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';
import { AuditRunResponse } from '../../shared/models/audit.models';

const BASE_URL = DEFAULT_API_CONFIG.baseUrl;

function makeRun(overrides: Partial<AuditRunResponse> = {}): AuditRunResponse {
  return {
    id: 'run-1',
    status: 'completed',
    entity_type: 'Streetlight',
    summary: {
      total_entities: 1,
      conformant_count: 0,
      non_conformant_count: 1,
      partial_count: 0,
      no_model_count: 0,
      schema_unavailable_count: 0,
    },
    started_at: '2026-09-01T10:00:00Z',
    finished_at: '2026-09-01T10:05:00Z',
    broker_url: 'http://orion:1026',
    reports: [],
    ...overrides,
  };
}

function setUpWithRoute(runId: string | null) {
  return TestBed.configureTestingModule({
    imports: [ReportDetailComponent],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap(runId ? { runId } : {}) } },
      },
    ],
  }).compileComponents();
}

describe('ReportDetailComponent', () => {
  let httpMock: HttpTestingController;

  afterEach(() => httpMock.verify());

  it('visually distinguishes structural (Nível 1) from semantic (Nível 2) violations', async () => {
    await setUpWithRoute('run-1');
    httpMock = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ReportDetailComponent);
    fixture.detectChanges();

    httpMock.expectOne(`${BASE_URL}/audits/run-1`).flush(
      makeRun({
        reports: [
          {
            entity_id: 'urn:ngsi-ld:Streetlight:001',
            entity_type: 'Streetlight',
            status: 'non_conformant',
            semantic_analysis_skipped: false,
            violations: [
              {
                attribute_path: 'temperature',
                severity: 'error',
                rule: 'required_property_missing',
                expected: 'temperature',
                found: null,
                message: 'ausente',
                detected_by: 'structural',
              },
              {
                attribute_path: 'temp',
                severity: 'warning',
                rule: 'synonym_detected',
                expected: 'temperature',
                found: 'temp',
                message: 'sinônimo conhecido',
                detected_by: 'semantic',
              },
            ],
            recommendations: [],
          },
        ],
      })
    );
    fixture.detectChanges();

    const html = (fixture.nativeElement as HTMLElement).innerHTML;
    expect(html).toContain('Nível 1');
    expect(html).toContain('Nível 2');
    const structuralEl = (fixture.nativeElement as HTMLElement).querySelector(
      '.violation__source--structural'
    );
    const semanticEl = (fixture.nativeElement as HTMLElement).querySelector(
      '.violation__source--semantic'
    );
    expect(structuralEl).toBeTruthy();
    expect(semanticEl).toBeTruthy();
  });

  it('explicitly communicates when semantic analysis was skipped, never omitting the section silently', async () => {
    await setUpWithRoute('run-1');
    httpMock = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ReportDetailComponent);
    fixture.detectChanges();

    httpMock.expectOne(`${BASE_URL}/audits/run-1`).flush(
      makeRun({
        reports: [
          {
            entity_id: 'urn:ngsi-ld:Streetlight:001',
            entity_type: 'Streetlight',
            status: 'conformant',
            semantic_analysis_skipped: true,
            violations: [],
            recommendations: [],
          },
        ],
      })
    );
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('não executada');
  });

  it('shows the diff view with the current value alongside the structured proposed_patch', async () => {
    await setUpWithRoute('run-1');
    httpMock = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ReportDetailComponent);
    fixture.detectChanges();

    httpMock.expectOne(`${BASE_URL}/audits/run-1`).flush(
      makeRun({
        reports: [
          {
            entity_id: 'urn:ngsi-ld:Streetlight:001',
            entity_type: 'Streetlight',
            status: 'partial',
            semantic_analysis_skipped: false,
            violations: [],
            recommendations: [
              {
                attribute_path: 'temp',
                action: 'rename_attribute',
                proposed_patch: { from: 'temp', to: 'temperature' },
                rationale: 'sinônimo conhecido',
                confidence: 0.9,
              },
            ],
          },
        ],
      })
    );
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('sinônimo conhecido');
    expect(text).toContain('"to": "temperature"');
  });
});
