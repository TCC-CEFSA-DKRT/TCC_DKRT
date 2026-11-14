from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm

from auditor.domain.entities.violation import ViolationSeverity
from auditor.infrastructure.reporting.severity_style import SeverityStyle

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 16 * mm
VERTICAL_MARGIN = MARGIN + 6 * mm
FRAME_PADDING = 6
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN - 2 * FRAME_PADDING
FRAME_HEIGHT = PAGE_HEIGHT - 2 * VERTICAL_MARGIN - 2 * FRAME_PADDING
BADGE_COLUMN_WIDTH = 18 * mm
CARD_BODY_WIDTH = CONTENT_WIDTH - BADGE_COLUMN_WIDTH
FIX_LABEL_WIDTH = 30 * mm

FIELD_MAX_CHARS = 1200
COMPACT_FIELD_MAX_CHARS = 300
IDENTIFIER_MAX_CHARS = 200

TEXT = colors.HexColor("#1A1D24")
MUTED = colors.HexColor("#5B6270")
BORDER = colors.HexColor("#C9CED6")
SURFACE = colors.HexColor("#F3F4F6")
ZEBRA = colors.HexColor("#F7F8FA")
ENTITY_BAND = colors.HexColor("#E4E7EC")
FIX_ACCENT = colors.HexColor("#0F6E5C")

SEVERITY_STYLES: dict[ViolationSeverity, SeverityStyle] = {
    ViolationSeverity.ERROR: SeverityStyle(
        fill=colors.HexColor("#7A1F1F"), text_hex="#FFFFFF", border=colors.HexColor("#7A1F1F")
    ),
    ViolationSeverity.WARNING: SeverityStyle(
        fill=colors.HexColor("#E0A21F"), text_hex="#1A1D24", border=colors.HexColor("#B57A0A")
    ),
    ViolationSeverity.INFO: SeverityStyle(
        fill=colors.HexColor("#FFFFFF"), text_hex="#2F5D8A", border=colors.HexColor("#2F5D8A")
    ),
}
RECOMMENDATION_STYLE = SeverityStyle(
    fill=colors.HexColor("#E6EFEC"), text_hex="#0F6E5C", border=FIX_ACCENT
)


def _paragraph_style(name: str, **overrides: object) -> ParagraphStyle:
    base: dict[str, object] = {
        "fontName": "Helvetica",
        "fontSize": 9,
        "leading": 12,
        "textColor": TEXT,
        "splitLongWords": True,
    }
    base.update(overrides)
    return ParagraphStyle(name, **base)


STYLES: dict[str, ParagraphStyle] = {
    "title": _paragraph_style(
        "title", fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=1.5 * mm
    ),
    "subtitle": _paragraph_style("subtitle", textColor=MUTED, spaceAfter=5 * mm),
    "h2": _paragraph_style(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=6 * mm,
        spaceAfter=2.5 * mm,
    ),
    "body": _paragraph_style("body"),
    "muted": _paragraph_style("muted", textColor=MUTED, fontSize=8.5, leading=11.5),
    "label": _paragraph_style("label", textColor=MUTED, fontSize=7.5, leading=9.5),
    "value": _paragraph_style("value", fontName="Helvetica-Bold", fontSize=9.5, leading=12),
    "tile_value": _paragraph_style(
        "tile_value", fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=TA_CENTER
    ),
    "tile_label": _paragraph_style(
        "tile_label", textColor=MUTED, fontSize=7.5, leading=9.5, alignment=TA_CENTER
    ),
    "table_head": _paragraph_style(
        "table_head", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED
    ),
    "table_head_num": _paragraph_style(
        "table_head_num",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=MUTED,
        alignment=TA_RIGHT,
    ),
    "table_cell": _paragraph_style("table_cell", fontSize=8.5, leading=11),
    "table_num": _paragraph_style("table_num", fontSize=8.5, leading=11, alignment=TA_RIGHT),
    "entity_id": _paragraph_style("entity_id", fontName="Helvetica-Bold", fontSize=10.5, leading=13),
    "entity_status": _paragraph_style(
        "entity_status", fontName="Helvetica-Bold", fontSize=9.5, leading=13, alignment=TA_RIGHT
    ),
    "group": _paragraph_style(
        "group", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED
    ),
    "badge": _paragraph_style(
        "badge", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_CENTER
    ),
    "badge_level": _paragraph_style("badge_level", fontSize=7, leading=9, alignment=TA_CENTER),
    "card_title": _paragraph_style("card_title", fontSize=10, leading=13),
    "diff_label": _paragraph_style("diff_label", textColor=MUTED, fontSize=7, leading=9),
    "diff_value": _paragraph_style("diff_value", fontName="Courier", fontSize=8.5, leading=11),
    "fix_head": _paragraph_style(
        "fix_head", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=FIX_ACCENT
    ),
    "fix_label": _paragraph_style(
        "fix_label", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=MUTED
    ),
    "fix_value": _paragraph_style("fix_value", fontSize=8.5, leading=11),
    "fix_code": _paragraph_style("fix_code", fontName="Courier", fontSize=8, leading=10.5),
}
