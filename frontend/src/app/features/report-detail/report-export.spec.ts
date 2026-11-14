import { HttpErrorResponse } from '@angular/common/http';
import { TimeoutError } from 'rxjs';

import { EXPORT_PDF_ERROR_MESSAGES } from './report-labels';
import { browserTimeZone, describeExportError } from './report-export';

describe('report-export', () => {
  it('uses the time zone the browser reports', () => {
    expect(browserTimeZone()).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  });

  it('falls back to UTC when the browser cannot tell its time zone', () => {
    spyOn(Intl, 'DateTimeFormat').and.throwError('unsupported');

    expect(browserTimeZone()).toBe('UTC');
  });

  it('maps each failure to a message without technical details', () => {
    const http = (status: number) => new HttpErrorResponse({ status });

    expect(describeExportError(new TimeoutError())).toBe(EXPORT_PDF_ERROR_MESSAGES.timeout);
    expect(describeExportError(http(0))).toBe(EXPORT_PDF_ERROR_MESSAGES.offline);
    expect(describeExportError(http(404))).toBe(EXPORT_PDF_ERROR_MESSAGES.notFound);
    expect(describeExportError(http(413))).toBe(EXPORT_PDF_ERROR_MESSAGES.tooLarge);
    expect(describeExportError(http(500))).toBe(EXPORT_PDF_ERROR_MESSAGES.generic);
    expect(describeExportError(new Error('x'))).toBe(EXPORT_PDF_ERROR_MESSAGES.generic);
  });
});
