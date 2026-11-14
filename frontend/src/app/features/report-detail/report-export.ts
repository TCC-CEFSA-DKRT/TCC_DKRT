import { HttpErrorResponse } from '@angular/common/http';
import { TimeoutError } from 'rxjs';

import { EXPORT_PDF_ERROR_MESSAGES } from './report-labels';

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function describeExportError(error: unknown): string {
  if (error instanceof TimeoutError) {
    return EXPORT_PDF_ERROR_MESSAGES.timeout;
  }
  const status = error instanceof HttpErrorResponse ? error.status : -1;
  switch (status) {
    case 0:
      return EXPORT_PDF_ERROR_MESSAGES.offline;
    case 404:
      return EXPORT_PDF_ERROR_MESSAGES.notFound;
    case 413:
      return EXPORT_PDF_ERROR_MESSAGES.tooLarge;
    default:
      return EXPORT_PDF_ERROR_MESSAGES.generic;
  }
}
