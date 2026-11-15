import { TestBed } from '@angular/core/testing';

import { FileDownloadService, filenameFromContentDisposition } from './file-download.service';

describe('filenameFromContentDisposition', () => {
  it('reads a quoted filename', () => {
    expect(filenameFromContentDisposition('attachment; filename="relatorio-streetlight.pdf"')).toBe(
      'relatorio-streetlight.pdf'
    );
  });

  it('reads an unquoted filename', () => {
    expect(filenameFromContentDisposition('attachment; filename=relatorio.pdf')).toBe('relatorio.pdf');
  });

  it('returns null when the header is missing or has no filename', () => {
    expect(filenameFromContentDisposition(null)).toBeNull();
    expect(filenameFromContentDisposition('attachment')).toBeNull();
  });
});

describe('FileDownloadService', () => {
  it('clicks a temporary link that points to the file and removes it afterwards', () => {
    const service = TestBed.inject(FileDownloadService);
    spyOn(URL, 'createObjectURL').and.returnValue('blob:fake-url');
    const clickSpy = spyOn(HTMLAnchorElement.prototype, 'click');

    service.save(new Blob(['%PDF'], { type: 'application/pdf' }), 'relatorio.pdf');

    expect(clickSpy).toHaveBeenCalledTimes(1);
    const link = clickSpy.calls.mostRecent().object as HTMLAnchorElement;
    expect(link.download).toBe('relatorio.pdf');
    expect(link.href).toBe('blob:fake-url');
    expect(document.body.contains(link)).toBeFalse();
  });
});
