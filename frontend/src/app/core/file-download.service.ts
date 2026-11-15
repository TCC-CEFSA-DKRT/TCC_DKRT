import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';

import { OBJECT_URL_RELEASE_DELAY_MS } from './file-download.constants';

@Injectable({ providedIn: 'root' })
export class FileDownloadService {
  private readonly document = inject(DOCUMENT);

  save(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const link = this.document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';
    this.document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), OBJECT_URL_RELEASE_DELAY_MS);
  }
}

export function filenameFromContentDisposition(header: string | null): string | null {
  const match = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match ? decodeURIComponent(match[1].trim()) : null;
}
