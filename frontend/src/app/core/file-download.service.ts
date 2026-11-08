import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';

/** Issue #23 — entrega um arquivo gerado pela API (ex.: o PDF do
 * relatório) como download do navegador. Isolado num serviço para que os
 * testes dos componentes não disparem downloads de verdade. */
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
    // Dá tempo ao navegador de iniciar o download antes de liberar a memória.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

/** Lê o nome do arquivo de um header `Content-Disposition` (ex.:
 * `attachment; filename="relatorio.pdf"`). */
export function filenameFromContentDisposition(header: string | null): string | null {
  const match = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match ? decodeURIComponent(match[1].trim()) : null;
}
