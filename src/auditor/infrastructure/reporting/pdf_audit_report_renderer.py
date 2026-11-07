"""PdfAuditReportRenderer — issue #23, decisao registrada na ADR-0022.

Gera o PDF do relatorio de uma auditoria com ReportLab (Python puro, sem
navegador nem bibliotecas de sistema), pronto para impressao em A4. A
organizacao segue a ordem em que o leitor procura a informacao:

1. Pagina de abertura: dados da auditoria (tenant, tipo, broker, datas,
   status), resumo agregado em quadros (status de conformidade e
   severidades) e a legenda.
2. Visao geral: uma tabela com uma linha por entidade (status e quantidade
   de erros, avisos, informacoes e recomendacoes) — para achar rapidamente
   o que precisa de atencao antes de ler o detalhe.
3. Detalhe por entidade (comeca em pagina nova): cada entidade tem uma
   faixa de titulo (repetida quando continua na pagina seguinte); cada
   violacao e' um cartao com selo de severidade, atributo, regra, mensagem,
   "Encontrado | Esperado" lado a lado e, quando existe, um quadro "Como
   corrigir" com acao, justificativa e correcao proposta do SLM.

Paginacao: quebra automatica, cabecalho e rodape em todas as paginas com
"Pagina X de Y". Escala de cinza: cada severidade tem o nome escrito no selo
(ERRO/AVISO/INFO) e um preenchimento com luminosidade bem diferente (quase
preto, cinza medio, branco com borda). Acentos: as fontes padrao do PDF
(Helvetica/Courier, codificacao WinAnsi) cobrem todo o portugues;
caracteres fora dessa tabela (ex.: emoji vindo do SLM) viram "?".
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone, tzinfo
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.entities.entity_report import EntityReport, SchemaSource
from auditor.domain.entities.recommendation import Recommendation
from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.infrastructure.reporting.labels import (
    ACTION_LABELS,
    CONFORMANCE_LABELS,
    CONFORMANCE_PRINT_ORDER,
    RUN_STATUS_LABELS,
    SEVERITY_BADGES,
    SEVERITY_ORDER,
    SEVERITY_PLURALS,
    rule_label,
)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 16 * mm
# O Frame do SimpleDocTemplate tem 6 pt de respiro de cada lado: as tabelas
# usam a mesma largura util dos paragrafos para ficarem alinhadas com eles.
FRAME_PADDING = 6
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN - 2 * FRAME_PADDING
BADGE_COLUMN_WIDTH = 18 * mm
CARD_BODY_WIDTH = CONTENT_WIDTH - BADGE_COLUMN_WIDTH
FIX_LABEL_WIDTH = 30 * mm

TEXT = colors.HexColor("#1A1D24")
MUTED = colors.HexColor("#5B6270")
BORDER = colors.HexColor("#C9CED6")
SURFACE = colors.HexColor("#F3F4F6")
ZEBRA = colors.HexColor("#F7F8FA")
ENTITY_BAND = colors.HexColor("#E4E7EC")


class SeverityStyle:
    def __init__(self, fill: str, text: str, border: str) -> None:
        self.fill = colors.HexColor(fill)
        self.text_hex = text
        self.border = colors.HexColor(border)


# Luminosidades bem separadas (ver test_severity_fills_stay_distinct_in_grayscale):
# ERRO quase preto, AVISO cinza medio, INFO branco com borda. Em cor, seguem
# a mesma familia da tela (vermelho / ambar / azul).
SEVERITY_STYLES: dict[ViolationSeverity, SeverityStyle] = {
    ViolationSeverity.ERROR: SeverityStyle(fill="#7A1F1F", text="#FFFFFF", border="#7A1F1F"),
    ViolationSeverity.WARNING: SeverityStyle(fill="#E0A21F", text="#1A1D24", border="#B57A0A"),
    ViolationSeverity.INFO: SeverityStyle(fill="#FFFFFF", text="#2F5D8A", border="#2F5D8A"),
}
RECOMMENDATION_STYLE = SeverityStyle(fill="#E6EFEC", text="#0F6E5C", border="#0F6E5C")


def _style(name: str, **overrides) -> ParagraphStyle:
    base = {
        "fontName": "Helvetica",
        "fontSize": 9,
        "leading": 12,
        "textColor": TEXT,
        "splitLongWords": True,
    }
    base.update(overrides)
    return ParagraphStyle(name, **base)


STYLES = {
    "title": _style("title", fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=1.5 * mm),
    "subtitle": _style("subtitle", textColor=MUTED, spaceAfter=5 * mm),
    "h2": _style("h2", fontName="Helvetica-Bold", fontSize=12, leading=15, spaceBefore=6 * mm, spaceAfter=2.5 * mm),
    "body": _style("body"),
    "muted": _style("muted", textColor=MUTED, fontSize=8.5, leading=11.5),
    "label": _style("label", textColor=MUTED, fontSize=7.5, leading=9.5),
    "value": _style("value", fontName="Helvetica-Bold", fontSize=9.5, leading=12),
    "tile_value": _style("tile_value", fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=TA_CENTER),
    "tile_label": _style("tile_label", textColor=MUTED, fontSize=7.5, leading=9.5, alignment=TA_CENTER),
    "table_head": _style("table_head", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED),
    "table_head_num": _style(
        "table_head_num", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED, alignment=TA_RIGHT
    ),
    "table_cell": _style("table_cell", fontSize=8.5, leading=11),
    "table_num": _style("table_num", fontSize=8.5, leading=11, alignment=TA_RIGHT),
    "entity_id": _style("entity_id", fontName="Helvetica-Bold", fontSize=10.5, leading=13),
    "entity_status": _style("entity_status", fontName="Helvetica-Bold", fontSize=9.5, leading=13, alignment=TA_RIGHT),
    "group": _style("group", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED),
    "badge": _style("badge", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_CENTER),
    "badge_level": _style("badge_level", fontSize=7, leading=9, alignment=TA_CENTER),
    "card_title": _style("card_title", fontSize=10, leading=13),
    "diff_label": _style("diff_label", textColor=MUTED, fontSize=7, leading=9),
    "diff_value": _style("diff_value", fontName="Courier", fontSize=8.5, leading=11),
    "fix_head": _style("fix_head", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor("#0F6E5C")),
    "fix_label": _style("fix_label", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=MUTED),
    "fix_value": _style("fix_value", fontSize=8.5, leading=11),
    "fix_code": _style("fix_code", fontName="Courier", fontSize=8, leading=10.5),
}


def safe_text(value: object) -> str:
    """Texto pronto para um Paragraph: so' caracteres que as fontes padrao
    do PDF sabem desenhar (WinAnsi cobre todo o portugues) e com &, < e >
    escapados (Paragraph interpreta uma marcacao parecida com HTML)."""
    text = "" if value is None else str(value)
    text = text.encode("cp1252", errors="replace").decode("cp1252")
    return escape(text)


class PdfAuditReportRenderer:
    media_type = "application/pdf"
    file_extension = "pdf"

    def render(self, run: AuditRun, *, display_timezone: tzinfo) -> bytes:
        generated_at = datetime.now(timezone.utc)
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN + 6 * mm,
            bottomMargin=MARGIN + 6 * mm,
            title=f"Relatório de auditoria — {_entity_type_label(run)}",
            author="DKRT — Auditoria de Data Spaces",
            subject=f"Auditoria {run.id}",
            creator="DKRT",
        )
        chrome = _PageChrome(
            header_left="DKRT · Relatório de auditoria de conformidade",
            header_right=f"{_entity_type_label(run)} · tenant {_tenant_label(run)}",
            footer_left=(
                f"Gerado em {_format_datetime(generated_at, display_timezone)} "
                f"({_timezone_name(display_timezone)})"
            ),
        )
        reports = _sorted_reports(run)
        story = [
            *self._header(run, display_timezone),
            *self._summary(run),
            *self._legend(),
            *self._overview(reports),
            *self._details(reports, display_timezone),
        ]
        document.build(story, canvasmaker=chrome.canvas_class())
        return buffer.getvalue()

    # -- pagina de abertura -----------------------------------------------------

    def _header(self, run: AuditRun, tz: tzinfo) -> list:
        fields = [
            ("Tenant (Fiware-Service)", _tenant_label(run)),
            ("Service path", run.tenant.fiware_service_path or "/"),
            ("Tipo de entidade", _entity_type_label(run)),
            ("Status da auditoria", RUN_STATUS_LABELS.get(run.status, run.status.value)),
            ("Início", _format_datetime(run.started_at, tz)),
            ("Término", _format_datetime(run.finished_at, tz) if run.finished_at else "—"),
            ("Context Broker", run.broker_url),
            ("Identificador da auditoria", str(run.id)),
        ]
        cells = [
            [
                [Paragraph(safe_text(label), STYLES["label"]), Paragraph(safe_text(value), STYLES["value"])]
                for label, value in fields[row : row + 2]
            ]
            for row in range(0, len(fields), 2)
        ]
        table = Table(cells, colWidths=[CONTENT_WIDTH / 2] * 2)
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story: list = [
            Paragraph("Relatório de auditoria de conformidade", STYLES["title"]),
            Paragraph(
                "Validação de entidades FIWARE (NGSI-v2) contra Smart Data Models — "
                "Nível 1 (validação estrutural) e Nível 2 (análise semântica com SLM).",
                STYLES["subtitle"],
            ),
            table,
        ]
        if run.failure_reason:
            story += [
                Spacer(1, 2 * mm),
                Paragraph(f"<b>Motivo da falha:</b> {safe_text(run.failure_reason)}", STYLES["body"]),
            ]
        return story

    def _summary(self, run: AuditRun) -> list:
        reports = run.reports
        total = len(reports)
        by_status = Counter(report.status for report in reports)
        statuses = [
            ConformanceStatus.CONFORMANT,
            ConformanceStatus.PARTIAL,
            ConformanceStatus.NON_CONFORMANT,
            ConformanceStatus.NO_MODEL_FOUND,
            ConformanceStatus.SCHEMA_UNAVAILABLE,
        ]
        status_tiles = [("Entidades", str(total))] + [
            (CONFORMANCE_LABELS[s], _count_with_percent(by_status[s], total)) for s in statuses
        ]
        by_severity = Counter(v.severity for report in reports for v in report.violations)
        recommendations = sum(len(report.recommendations) for report in reports)
        severity_tiles = [(SEVERITY_PLURALS[s], str(by_severity[s])) for s in SEVERITY_ORDER]
        severity_tiles.append(("Recomendações do SLM", str(recommendations)))
        return [
            Paragraph("Resumo", STYLES["h2"]),
            Paragraph("Entidades por status de conformidade", STYLES["label"]),
            Spacer(1, 1 * mm),
            _tiles(status_tiles, highlight_first=True),
            Spacer(1, 3 * mm),
            Paragraph("Violações encontradas e recomendações", STYLES["label"]),
            Spacer(1, 1 * mm),
            _tiles(severity_tiles, severities=list(SEVERITY_ORDER) + [None]),
        ]

    def _legend(self) -> list:
        items = [
            (ViolationSeverity.ERROR, "torna a entidade não conforme"),
            (ViolationSeverity.WARNING, "a entidade fica parcialmente conforme"),
            (ViolationSeverity.INFO, "observação sem impacto no status"),
        ]
        row = []
        widths = []
        for severity, description in items:
            row += [_badge_cell(severity), Paragraph(safe_text(description), STYLES["muted"])]
            widths += [BADGE_COLUMN_WIDTH, CONTENT_WIDTH / 3 - BADGE_COLUMN_WIDTH]
        table = Table([row], colWidths=widths)
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (1, 0), (-1, -1), 6),
        ]
        for index, (severity, _) in enumerate(items):
            style = SEVERITY_STYLES[severity]
            commands += [
                ("BACKGROUND", (index * 2, 0), (index * 2, 0), style.fill),
                ("BOX", (index * 2, 0), (index * 2, 0), 0.8, style.border),
            ]
        table.setStyle(TableStyle(commands))
        return [
            Paragraph("Legenda", STYLES["h2"]),
            table,
            Spacer(1, 2 * mm),
            Paragraph(
                "<b>Nível 1</b> = validação estrutural contra o schema do Smart Data Model. "
                "<b>Nível 2</b> = análise semântica feita pelo modelo de linguagem (SLM).",
                STYLES["muted"],
            ),
        ]

    # -- visao geral -------------------------------------------------------------

    def _overview(self, reports: list[EntityReport]) -> list:
        if not reports:
            return []
        head = [
            Paragraph("Entidade", STYLES["table_head"]),
            Paragraph("Status", STYLES["table_head"]),
            Paragraph("Erros", STYLES["table_head_num"]),
            Paragraph("Avisos", STYLES["table_head_num"]),
            Paragraph("Info.", STYLES["table_head_num"]),
            Paragraph("Recom.", STYLES["table_head_num"]),
        ]
        rows = [head]
        for report in reports:
            counts = Counter(v.severity for v in report.violations)
            rows.append(
                [
                    Paragraph(safe_text(report.entity_id), STYLES["table_cell"]),
                    Paragraph(safe_text(CONFORMANCE_LABELS.get(report.status, report.status.value)), STYLES["table_cell"]),
                    *(
                        Paragraph(_count_or_dash(counts[s]), STYLES["table_num"])
                        for s in SEVERITY_ORDER
                    ),
                    Paragraph(_count_or_dash(len(report.recommendations)), STYLES["table_num"]),
                ]
            )
        number_width = 15 * mm
        status_width = 30 * mm
        table = Table(
            rows,
            colWidths=[CONTENT_WIDTH - status_width - 4 * number_width, status_width] + [number_width] * 4,
            repeatRows=1,
        )
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, MUTED),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for row in range(2, len(rows), 2):
            commands.append(("BACKGROUND", (0, row), (-1, row), ZEBRA))
        table.setStyle(TableStyle(commands))
        return [
            Paragraph("Visão geral das entidades", STYLES["h2"]),
            Paragraph(
                "Ordenadas por status — as que precisam de correção aparecem primeiro. "
                "O detalhe de cada entidade vem a seguir, na mesma ordem.",
                STYLES["muted"],
            ),
            Spacer(1, 2 * mm),
            table,
        ]

    # -- detalhe por entidade ---------------------------------------------------

    def _details(self, reports: list[EntityReport], tz: tzinfo) -> list:
        if not reports:
            return [
                Paragraph("Detalhe por entidade", STYLES["h2"]),
                Paragraph("Esta auditoria não encontrou nenhuma entidade.", STYLES["body"]),
            ]
        story: list = [PageBreak(), Paragraph("Detalhe por entidade", STYLES["h2"])]
        for report in reports:
            story.extend(self._entity(report, tz))
            story.append(Spacer(1, 6 * mm))
        return story

    def _entity(self, report: EntityReport, tz: tzinfo) -> list:
        band = _entity_band(report)
        notes = [_schema_origin_text(report, tz)]
        validated = report.status not in (
            ConformanceStatus.NO_MODEL_FOUND,
            ConformanceStatus.SCHEMA_UNAVAILABLE,
        )
        if report.semantic_analysis_skipped and validated:
            notes.append(
                "Análise semântica (Nível 2) não executada para esta entidade — o diagnóstico "
                "reflete apenas a validação estrutural (Nível 1)."
            )
        if validated and not report.violations:
            notes.append('<font color="#1A1D24"><b>Nenhuma violação encontrada.</b></font>')
        intro = Paragraph("<br/>".join(notes), STYLES["muted"])

        rows: list = [[band], [intro]]
        row_kinds: list[str] = ["band", "intro"]
        pending = list(report.recommendations)
        for severity in SEVERITY_ORDER:
            violations = [v for v in report.violations if v.severity == severity]
            if not violations:
                continue
            rows.append([Paragraph(f"{SEVERITY_PLURALS[severity].upper()} ({len(violations)})", STYLES["group"])])
            row_kinds.append("group")
            for violation in violations:
                matched = [rec for rec in pending if rec.attribute_path == violation.attribute_path]
                for rec in matched:
                    pending.remove(rec)
                rows.append([_violation_card(violation, matched)])
                row_kinds.append("card")
        if pending:
            rows.append([Paragraph(f"OUTRAS RECOMENDAÇÕES ({len(pending)})", STYLES["group"])])
            row_kinds.append("group")
            rows += [[_recommendation_card(rec)] for rec in pending]
            row_kinds += ["card"] * len(pending)

        # A faixa com o nome da entidade e' a primeira linha da tabela e se
        # repete (repeatRows=1) quando os cartoes continuam na pagina
        # seguinte — no papel, toda pagina diz de qual entidade se trata.
        table = Table(rows, colWidths=[CONTENT_WIDTH], repeatRows=1)
        commands = [
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]
        for index, kind in enumerate(row_kinds):
            if kind == "intro":
                commands += [("TOPPADDING", (0, index), (0, index), 4), ("BOTTOMPADDING", (0, index), (0, index), 2)]
            elif kind == "group":
                commands += [("TOPPADDING", (0, index), (0, index), 6), ("BOTTOMPADDING", (0, index), (0, index), 3)]
            elif kind == "card":
                commands.append(("BOTTOMPADDING", (0, index), (0, index), 4))
        table.setStyle(TableStyle(commands))
        if len(rows) <= 4:
            return [KeepTogether([table])]
        return [table]


class _PageChrome:
    """Cabecalho e rodape repetidos em todas as paginas, com "Pagina X de Y".
    O total de paginas so' e' conhecido no fim, entao cada pagina e' guardada
    e desenhada quando o documento termina (padrao "NumberedCanvas" do
    ReportLab)."""

    def __init__(self, header_left: str, header_right: str, footer_left: str) -> None:
        self.header_left = _pdf_safe(header_left)
        self.header_right = _pdf_safe(header_right)
        self.footer_left = _pdf_safe(footer_left)

    def canvas_class(self):
        chrome = self

        class _NumberedCanvas(canvas.Canvas):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self._pages: list[dict] = []

            def showPage(self) -> None:  # noqa: N802 (nome da API do ReportLab)
                self._pages.append(dict(self.__dict__))
                self._startPage()

            def save(self) -> None:
                total = len(self._pages)
                for page in self._pages:
                    self.__dict__.update(page)
                    chrome.draw(self, total)
                    super().showPage()
                super().save()

        return _NumberedCanvas

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
        pdf.drawRightString(right, MARGIN - 1 * mm, f"Página {pdf.getPageNumber()} de {total_pages}")
        pdf.restoreState()


# -- blocos reutilizados -------------------------------------------------------


def _tiles(tiles: list[tuple[str, str]], *, highlight_first: bool = False, severities=None) -> Table:
    """Quadros "numero grande + rotulo". Com `severities`, cada quadro ganha
    uma barra superior na cor/tom da severidade correspondente."""
    width = CONTENT_WIDTH / len(tiles)
    table = Table(
        [
            [Paragraph(safe_text(value), STYLES["tile_value"]) for _, value in tiles],
            [Paragraph(safe_text(label), STYLES["tile_label"]) for label, _ in tiles],
        ],
        colWidths=[width] * len(tiles),
    )
    commands = [
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LINEAFTER", (0, 0), (-2, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
    ]
    if highlight_first:
        commands.append(("BACKGROUND", (0, 0), (0, -1), SURFACE))
    for column, severity in enumerate(severities or []):
        style = SEVERITY_STYLES[severity] if severity is not None else RECOMMENDATION_STYLE
        commands.append(("LINEABOVE", (column, 0), (column, 0), 3, style.border))
    table.setStyle(TableStyle(commands))
    return table


def _badge_cell(severity: ViolationSeverity | None, level: str | None = None) -> list:
    style = SEVERITY_STYLES[severity] if severity is not None else RECOMMENDATION_STYLE
    label = SEVERITY_BADGES[severity] if severity is not None else "SLM"
    cell = [Paragraph(f'<font color="{style.text_hex}">{label}</font>', STYLES["badge"])]
    if level:
        cell.append(Paragraph(f'<font color="{style.text_hex}">{level}</font>', STYLES["badge_level"]))
    return cell


def _entity_band(report: EntityReport) -> Table:
    status = CONFORMANCE_LABELS.get(report.status, report.status.value)
    band = Table(
        [
            [
                Paragraph(safe_text(report.entity_id), STYLES["entity_id"]),
                Paragraph(f'<font color="#5B6270" name="Helvetica">Status:</font> {safe_text(status)}', STYLES["entity_status"]),
            ]
        ],
        colWidths=[CONTENT_WIDTH - 50 * mm, 50 * mm],
    )
    band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ENTITY_BAND),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return band


def _violation_card(violation: Violation, recommendations: list[Recommendation]) -> Table:
    level = "Nível 1" if violation.detected_by == DetectionSource.STRUCTURAL else "Nível 2"
    body = [
        Paragraph(
            f"<b>{safe_text(violation.attribute_path)}</b> &nbsp;·&nbsp; {safe_text(rule_label(violation.rule))}",
            STYLES["card_title"],
        ),
        Spacer(1, 1 * mm),
        Paragraph(safe_text(violation.message), STYLES["body"]),
        Spacer(1, 2 * mm),
        _found_expected(violation),
    ]
    for rec in recommendations:
        body += [Spacer(1, 2 * mm), _fix_panel(rec)]
    return _card(_badge_cell(violation.severity, level), body, SEVERITY_STYLES[violation.severity])


def _recommendation_card(rec: Recommendation) -> Table:
    body = [
        Paragraph(
            f"<b>{safe_text(rec.attribute_path)}</b> &nbsp;·&nbsp; recomendação sem violação correspondente",
            STYLES["card_title"],
        ),
        Spacer(1, 2 * mm),
        _fix_panel(rec),
    ]
    return _card(_badge_cell(None, "Nível 2"), body, RECOMMENDATION_STYLE)


def _card(badge: list, body: list, style: SeverityStyle) -> Table:
    card = Table([[badge, body]], colWidths=[BADGE_COLUMN_WIDTH, CARD_BODY_WIDTH])
    card.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, 0), style.fill),
                ("LINEBEFORE", (0, 0), (0, 0), 0.8, style.border),
                ("LINEABOVE", (0, 0), (0, 0), 0.8, style.border),
                ("LINEBELOW", (0, 0), (0, 0), 0.8, style.border),
                ("BOX", (1, 0), (1, 0), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (1, 0), (1, 0), 8),
                ("RIGHTPADDING", (1, 0), (1, 0), 8),
            ]
        )
    )
    return card


def _found_expected(violation: Violation) -> Table:
    inner = CARD_BODY_WIDTH - 16
    table = Table(
        [
            [Paragraph("ENCONTRADO", STYLES["diff_label"]), Paragraph("ESPERADO", STYLES["diff_label"])],
            [
                Paragraph(safe_text(_missing_if_none(violation.found)), STYLES["diff_value"]),
                Paragraph(safe_text(_missing_if_none(violation.expected)), STYLES["diff_value"]),
            ],
        ],
        colWidths=[inner / 2, inner / 2],
    )
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, -1), 0.5, BORDER),
                ("BOX", (1, 0), (1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _fix_panel(rec: Recommendation) -> Table:
    inner = CARD_BODY_WIDTH - 16
    action = ACTION_LABELS.get(rec.action, rec.action.value)
    patch = json.dumps(rec.proposed_patch, ensure_ascii=False)
    table = Table(
        [
            [
                Paragraph(
                    f"Como corrigir: {safe_text(action)} "
                    f'<font name="Helvetica" color="#5B6270">— recomendação do SLM, '
                    f"confiança {round(rec.confidence * 100)}%</font>",
                    STYLES["fix_head"],
                ),
                "",
            ],
            [Paragraph("Justificativa", STYLES["fix_label"]), Paragraph(safe_text(rec.rationale), STYLES["fix_value"])],
            [Paragraph("Correção proposta", STYLES["fix_label"]), Paragraph(safe_text(patch), STYLES["fix_code"])],
        ],
        colWidths=[FIX_LABEL_WIDTH, inner - FIX_LABEL_WIDTH],
    )
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, RECOMMENDATION_STYLE.border),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 1), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ]
        )
    )
    return table


# -- helpers ----------------------------------------------------------------------


def _sorted_reports(run: AuditRun) -> list[EntityReport]:
    order = {status: index for index, status in enumerate(CONFORMANCE_PRINT_ORDER)}
    return sorted(run.reports, key=lambda r: (order.get(r.status, len(order)), r.entity_id))


def _schema_origin_text(report: EntityReport, tz: tzinfo) -> str:
    model = report.data_model
    model_text = f"{safe_text(model.model_name)} v{safe_text(model.version)}" if model else ""
    if report.schema_origin is not None:
        when = _format_datetime(report.schema_origin.fetched_at, tz)
        if report.schema_origin.source == SchemaSource.LIVE:
            return f"Schema {model_text} obtido ao vivo em {when}."
        return (
            f"<b>Schema {model_text} obtido do cache em {when}</b> — o catálogo não respondeu "
            "durante a auditoria, por isso foi usada a última cópia salva."
        )
    if report.status == ConformanceStatus.NO_MODEL_FOUND:
        return "Nenhum Smart Data Model corresponde a este tipo de entidade; a validação não foi executada."
    if report.status == ConformanceStatus.SCHEMA_UNAVAILABLE:
        return (
            f"O schema {model_text} não pôde ser obtido (nem ao vivo, nem do cache); "
            "a validação não foi executada."
        )
    return "Origem do schema não registrada neste relatório."


def _pdf_safe(text: str) -> str:
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _missing_if_none(value: str | None) -> str:
    return "(ausente)" if value is None else value


def _count_with_percent(count: int, total: int) -> str:
    if not total:
        return "0"
    return f"{count} ({round(count * 100 / total)}%)"


def _count_or_dash(count: int) -> str:
    return str(count) if count else "—"


def _entity_type_label(run: AuditRun) -> str:
    return run.entity_type.value if run.entity_type else "Todos os tipos"


def _tenant_label(run: AuditRun) -> str:
    return run.tenant.fiware_service or "(padrão)"


def _format_datetime(value: datetime, tz: tzinfo) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz).strftime("%d/%m/%Y %H:%M")


def _timezone_name(tz: tzinfo) -> str:
    return getattr(tz, "key", None) or tz.tzname(None) or "UTC"
