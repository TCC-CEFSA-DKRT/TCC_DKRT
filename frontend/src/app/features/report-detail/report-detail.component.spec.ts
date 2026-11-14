import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap } from '@angular/router';

import { ReportDetailComponent } from './report-detail.component';
import { API_CONFIG, DEFAULT_API_CONFIG } from '../../core/api-config';
import { FileDownloadService } from '../../core/file-download.service';
import { AuditRunResponse, EntityReportResponse } from '../../shared/models/audit.models';

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
      // Issue #23: nenhum teste dispara um download de verdade.
      { provide: FileDownloadService, useValue: jasmine.createSpyObj('FileDownloadService', ['save']) },
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap(runId ? { runId } : {}) } },
      },
    ],
  }).compileComponents();
}

function makeReport(overrides: Partial<EntityReportResponse> = {}): EntityReportResponse {
  return {
    entity_id: 'urn:ngsi-ld:Streetlight:001',
    entity_type: 'Streetlight',
    status: 'conformant',
    semantic_analysis_skipped: false,
    violations: [],
    recommendations: [],
    data_model: {
      subject: 'dataModel.Streetlighting',
      model_name: 'Streetlight',
      version: '0.1.1',
      schema_url: 'https://example.org/Streetlight/schema.json',
    },
    schema_origin: { source: 'live', fetched_at: '2026-10-20T12:00:00Z' },
    ...overrides,
  };
}

/** Monta a tela com um run contendo `reports` e devolve o elemento raiz. */
async function renderReports(reports: EntityReportResponse[]) {
  await setUpWithRoute('run-1');
  const httpMock = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(ReportDetailComponent);
  fixture.detectChanges();
  httpMock.expectOne(`${BASE_URL}/audits/run-1`).flush(makeRun({ reports }));
  fixture.detectChanges();
  return { fixture, httpMock, element: fixture.nativeElement as HTMLElement };
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

  describe('issue #22', () => {
    it('groups violations by severity, most severe first, with Portuguese titles and counts', async () => {
      const view = await renderReports([
        makeReport({
          status: 'non_conformant',
          violations: [
            { attribute_path: 'a', severity: 'info', rule: 'r', expected: null, found: null, message: 'm', detected_by: 'semantic' },
            { attribute_path: 'b', severity: 'error', rule: 'type_mismatch', expected: 'number', found: 'string', message: 'm', detected_by: 'structural' },
            { attribute_path: 'c', severity: 'warning', rule: 'r', expected: null, found: null, message: 'm', detected_by: 'semantic' },
            { attribute_path: 'd', severity: 'error', rule: 'format_invalid', expected: 'date-time', found: 'ontem', message: 'm', detected_by: 'structural' },
          ],
        }),
      ]);
      httpMock = view.httpMock;

      const titles = Array.from(view.element.querySelectorAll('.violation-group__title')).map((el) =>
        el.textContent?.trim()
      );
      expect(titles).toEqual(['Erros (2)', 'Avisos (1)', 'Informações (1)']);
    });

    it('shows the attribute, the violated rule, found × expected and the fix in the same block', async () => {
      const view = await renderReports([
        makeReport({
          status: 'non_conformant',
          violations: [
            {
              attribute_path: 'temperature',
              severity: 'error',
              rule: 'type_mismatch',
              expected: 'number',
              found: 'string',
              message: 'tipo incorreto',
              detected_by: 'structural',
            },
          ],
          recommendations: [
            {
              attribute_path: 'temperature',
              action: 'fix_type',
              proposed_patch: { attribute: 'temperature', type: 'Number' },
              rationale: 'O modelo define temperature como número.',
              confidence: 0.87,
            },
          ],
        }),
      ]);
      httpMock = view.httpMock;

      const violation = view.element.querySelector('.violation')!;
      const text = violation.textContent ?? '';
      expect(violation.querySelector('.violation__path')?.textContent).toContain('temperature');
      expect(violation.querySelector('.violation__rule')?.textContent).toContain('Tipo de dado incorreto');
      expect(text).toContain('Encontrado');
      expect(text).toContain('Esperado');
      // A recomendação fica dentro do bloco da violação que ela corrige.
      const fix = violation.querySelector('.recommendation');
      expect(fix).not.toBeNull();
      expect(fix?.textContent).toContain('Corrigir o tipo de dado');
      expect(fix?.textContent).toContain('O modelo define temperature como número.');
      expect(fix?.textContent).toContain('87%');
      expect(fix?.textContent).toContain('"type": "Number"');
      expect(view.element.textContent).not.toContain('Outras recomendações');
    });

    it('shows the schema origin: live with the fetch date, cache highlighted as cache', async () => {
      const view = await renderReports([
        makeReport({ entity_id: 'live-1' }),
        makeReport({
          entity_id: 'cache-1',
          schema_origin: { source: 'cache', fetched_at: '2026-10-01T12:00:00Z' },
        }),
      ]);
      httpMock = view.httpMock;

      const origins = view.element.querySelectorAll('.schema-origin');
      expect(origins[0].textContent).toContain('ao vivo em 20/10/2026');
      expect(origins[0].textContent).toContain('Streetlight v0.1.1');
      expect(origins[0].classList).not.toContain('schema-origin--cache');
      expect(origins[1].textContent).toContain('do cache em 01/10/2026');
      expect(origins[1].classList).toContain('schema-origin--cache');
    });

    it('explains when there is no model, without claiming the entity is conformant', async () => {
      const view = await renderReports([
        makeReport({
          status: 'no_model_found',
          semantic_analysis_skipped: true,
          data_model: null,
          schema_origin: null,
        }),
      ]);
      httpMock = view.httpMock;

      const text = view.element.textContent ?? '';
      expect(text).toContain('Nenhum Smart Data Model corresponde a este tipo');
      expect(text).not.toContain('Nenhuma violação encontrada');
      expect(view.element.querySelector('.semantic-skipped-note')).toBeNull();
    });

    it('filters entities by status and shows the count of each option', async () => {
      const view = await renderReports([
        makeReport({ entity_id: 'ok-1', status: 'conformant' }),
        makeReport({
          entity_id: 'bad-1',
          status: 'non_conformant',
          violations: [
            { attribute_path: 'x', severity: 'error', rule: 'type_mismatch', expected: null, found: null, message: 'm', detected_by: 'structural' },
          ],
        }),
        makeReport({ entity_id: 'none-1', status: 'no_model_found', data_model: null, schema_origin: null }),
      ]);
      httpMock = view.httpMock;
      const option = (value: string) =>
        view.element.querySelector(`[data-filter="${value}"]`) as HTMLButtonElement;

      expect(option('all').textContent).toContain('3');
      expect(option('non_conformant').textContent).toContain('1');
      expect(option('partial').textContent).toContain('0');
      expect(option('no_model_found').textContent).toContain('Sem modelo');
      expect(view.element.querySelector('[data-filter="schema_unavailable"]')).toBeNull();

      option('non_conformant').click();
      view.fixture.detectChanges();
      let ids = Array.from(view.element.querySelectorAll('.entity-report__id')).map((el) => el.textContent);
      expect(ids).toEqual(['bad-1']);
      expect(option('non_conformant').getAttribute('aria-pressed')).toBe('true');

      option('partial').click();
      view.fixture.detectChanges();
      expect(view.element.querySelectorAll('.entity-report').length).toBe(0);
      expect(view.element.textContent).toContain('Nenhuma entidade com o status parcial');

      option('all').click();
      view.fixture.detectChanges();
      ids = Array.from(view.element.querySelectorAll('.entity-report__id')).map((el) => el.textContent);
      expect(ids).toEqual(['ok-1', 'bad-1', 'none-1']);
    });

    it('states that no violation was found for a conformant entity', async () => {
      const view = await renderReports([makeReport()]);
      httpMock = view.httpMock;

      expect(view.element.textContent).toContain('Nenhuma violação encontrada.');
    });
  });

  describe('issue #23 — exportar PDF', () => {
    const PDF_URL = `${BASE_URL}/audits/run-1/report.pdf`;
    const exportButton = (element: HTMLElement) =>
      element.querySelector('.export-button') as HTMLButtonElement;

    it('downloads the PDF of the whole audit with the browser time zone and the server filename', async () => {
      const view = await renderReports([makeReport()]);
      httpMock = view.httpMock;
      const downloads = TestBed.inject(FileDownloadService) as jasmine.SpyObj<FileDownloadService>;

      exportButton(view.element).click();
      view.fixture.detectChanges();

      const req = httpMock.expectOne((r) => r.url === PDF_URL);
      expect(req.request.responseType).toBe('blob');
      expect(req.request.params.get('tz')).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
      const pdf = new Blob(['%PDF-1.4'], { type: 'application/pdf' });
      req.flush(pdf, {
        headers: { 'Content-Disposition': 'attachment; filename="relatorio-streetlight-2026-10-24-1405.pdf"' },
      });
      view.fixture.detectChanges();

      expect(downloads.save).toHaveBeenCalledOnceWith(pdf, 'relatorio-streetlight-2026-10-24-1405.pdf');
      expect(exportButton(view.element).disabled).toBeFalse();
      expect(exportButton(view.element).textContent).toContain('Exportar PDF');
    });

    it('shows progress and ignores extra clicks while the PDF is being generated', async () => {
      const view = await renderReports([makeReport()]);
      httpMock = view.httpMock;

      exportButton(view.element).click();
      view.fixture.detectChanges();
      exportButton(view.element).click();

      expect(exportButton(view.element).disabled).toBeTrue();
      expect(exportButton(view.element).textContent).toContain('Gerando PDF');
      expect(view.element.querySelector('.export-status')?.textContent).toContain('alguns segundos');
      const requests = httpMock.match((r) => r.url === PDF_URL);
      expect(requests.length).toBe(1);
      requests[0].flush(new Blob(['%PDF']));
    });

    it('shows a clear message when the export fails and lets the user try again', async () => {
      const view = await renderReports([makeReport()]);
      httpMock = view.httpMock;
      const downloads = TestBed.inject(FileDownloadService) as jasmine.SpyObj<FileDownloadService>;

      exportButton(view.element).click();
      httpMock
        .expectOne((r) => r.url === PDF_URL)
        .flush(new Blob(['Internal Server Error']), { status: 500, statusText: 'Server Error' });
      view.fixture.detectChanges();

      const alert = view.element.querySelector('[role="alert"]');
      expect(alert?.textContent).toContain('Não foi possível gerar o PDF');
      expect(alert?.textContent).not.toContain('500');
      expect(downloads.save).not.toHaveBeenCalled();
      expect(exportButton(view.element).disabled).toBeFalse();
    });
  });
});
