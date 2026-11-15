from __future__ import annotations

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from auditor.infrastructure.reporting.pdf_text import pdf_safe
from auditor.infrastructure.reporting.pdf_theme import (
    BORDER,
    FRAME_PADDING,
    MARGIN,
    MUTED,
    PAGE_HEIGHT,
    PAGE_WIDTH,
)


class PageChrome:
    def __init__(self, header_left: str, header_right: str, footer_left: str) -> None:
        self.header_left = pdf_safe(header_left)
        self.header_right = pdf_safe(header_right)
        self.footer_left = pdf_safe(footer_left)

    def canvas_class(self) -> type[canvas.Canvas]:
        chrome = self

        class NumberedCanvas(canvas.Canvas):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self._pages: list[dict] = []

            def showPage(self) -> None:  # noqa: N802
                self._pages.append(dict(self.__dict__))
                self._startPage()

            def save(self) -> None:
                total = len(self._pages)
                for page in self._pages:
                    self.__dict__.update(page)
                    chrome.draw(self, total)
                    super().showPage()
                super().save()

        return NumberedCanvas

    def draw(self, pdf: canvas.Canvas, total_pages: int) -> None:
        pdf.saveState()
        left, right = MARGIN + FRAME_PADDING, PAGE_WIDTH - MARGIN - FRAME_PADDING
        top = PAGE_HEIGHT - MARGIN
        pdf.setStrokeColor(BORDER)
        pdf.setLineWidth(0.5)
        pdf.line(left, top - 2 * mm, right, top - 2 * mm)
        pdf.line(left, MARGIN + 2 * mm, right, MARGIN + 2 * mm)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(left, top, self.header_left)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawRightString(right, top, self.header_right)
        pdf.drawString(left, MARGIN - 1 * mm, self.footer_left)
        pdf.drawRightString(
            right, MARGIN - 1 * mm, f"Página {pdf.getPageNumber()} de {total_pages}"
        )
        pdf.restoreState()
