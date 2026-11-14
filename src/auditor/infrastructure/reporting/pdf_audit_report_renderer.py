from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable
from functools import partial
from datetime import datetime, timezone, tzinfo
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
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
)
from auditor.infrastructure.reporting.pdf_page_chrome import PageChrome
from auditor.infrastructure.reporting.pdf_text import (
    normalized_attribute_path,
    rule_label,
    safe_text,
)
from auditor.infrastructure.reporting.pdf_theme import (
    BADGE_COLUMN_WIDTH,
    BORDER,
    CARD_BODY_WIDTH,
    COMPACT_FIELD_MAX_CHARS,
    CONTENT_WIDTH,
    ENTITY_BAND,
    FIELD_MAX_CHARS,
    FIX_LABEL_WIDTH,
    FRAME_HEIGHT,
    IDENTIFIER_MAX_CHARS,
    MARGIN,
    MUTED,
    RECOMMENDATION_STYLE,
    SEVERITY_STYLES,
    STYLES,
    SURFACE,
    VERTICAL_MARGIN,
    ZEBRA,
)
from auditor.infrastructure.reporting.severity_style import SeverityStyle

logger = logging.getLogger(__name__)

CardBuilder = Callable[[int], Table]


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
            topMargin=VERTICAL_MARGIN,
            bottomMargin=VERTICAL_MARGIN,
            title=f"Relatório de auditoria — {_entity_type_label(run)}",
            author="DKRT — Auditoria de Data Spaces",
            subject=f"Auditoria {run.id}",
            creator="DKRT",
        )
        chrome = PageChrome(
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

    def _header(self, run: AuditRun, tz: tzinfo) -> list[Flowable]:
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
                [
                    Paragraph(safe_text(label), STYLES["label"]),
                    Paragraph(safe_text(value, IDENTIFIER_MAX_CHARS), STYLES["value"]),
                ]
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
        story: list[Flowable] = [
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
                Paragraph(
                    f"<b>Motivo da falha:</b> {safe_text(run.failure_reason)}", STYLES["body"]
                ),
            ]
        return story

    def _summary(self, run: AuditRun) -> list[Flowable]:
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
            _tiles(severity_tiles, severities=[*SEVERITY_ORDER, None]),
        ]

    def _legend(self) -> list[Flowable]:
        items = [
            (ViolationSeverity.ERROR, "torna a entidade não conforme"),
            (ViolationSeverity.WARNING, "a entidade fica parcialmente conforme"),
            (ViolationSeverity.INFO, "observação sem impacto no status"),
        ]
        row: list[Any] = []
        widths: list[float] = []
        for severity, description in items:
            row += [_badge_cell(severity), Paragraph(safe_text(description), STYLES["muted"])]
            widths += [BADGE_COLUMN_WIDTH, CONTENT_WIDTH / 3 - BADGE_COLUMN_WIDTH]
        table = Table([row], colWidths=widths)
        commands: list[tuple[Any, ...]] = [
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

    def _overview(self, reports: list[EntityReport]) -> list[Flowable]:
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
        rows: list[list[Any]] = [head]
        for report in reports:
            counts = Counter(v.severity for v in report.violations)
            rows.append(
                [
                    Paragraph(
                        safe_text(report.entity_id, IDENTIFIER_MAX_CHARS), STYLES["table_cell"]
                    ),
                    Paragraph(safe_text(_status_label(report)), STYLES["table_cell"]),
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
            colWidths=[CONTENT_WIDTH - status_width - 4 * number_width, status_width]
            + [number_width] * 4,
            repeatRows=1,
        )
        commands: list[tuple[Any, ...]] = [
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

    def _details(self, reports: list[EntityReport], tz: tzinfo) -> list[Flowable]:
        if not reports:
            return [
                Paragraph("Detalhe por entidade", STYLES["h2"]),
                Paragraph("Esta auditoria não encontrou nenhuma entidade.", STYLES["body"]),
            ]
        story: list[Flowable] = [PageBreak(), Paragraph("Detalhe por entidade", STYLES["h2"])]
        for report in reports:
            story.extend(self._entity_or_fallback(report, tz))
            story.append(Spacer(1, 6 * mm))
        return story

    def _entity_or_fallback(self, report: EntityReport, tz: tzinfo) -> list[Flowable]:
        try:
            return self._entity(report, tz)
        except Exception:
            logger.exception(
                "Falha ao montar o detalhe da entidade %s no PDF; usando o aviso no lugar",
                report.entity_id,
            )
            return [
                KeepTogether(
                    [
                        _entity_band(report),
                        Spacer(1, 1.5 * mm),
                        Paragraph(
                            "Não foi possível montar o detalhe desta entidade no PDF. "
                            "Consulte a tela de relatório para ver as violações e as "
                            "recomendações.",
                            STYLES["muted"],
                        ),
                    ]
                )
            ]

    def _entity(self, report: EntityReport, tz: tzinfo) -> list[Flowable]:
        band = _entity_band(report)
        _, band_height = band.wrap(CONTENT_WIDTH, FRAME_HEIGHT)
        max_card_height = FRAME_HEIGHT - band_height - 8
        intro = Paragraph("<br/>".join(_entity_notes(report, tz)), STYLES["muted"])

        rows: list[list[Any]] = [[band], [intro]]
        row_kinds: list[str] = ["band", "intro"]
        pending = list(report.recommendations)
        for severity in SEVERITY_ORDER:
            violations = [v for v in report.violations if v.severity == severity]
            if not violations:
                continue
            rows.append(
                [
                    Paragraph(
                        f"{SEVERITY_PLURALS[severity].upper()} ({len(violations)})",
                        STYLES["group"],
                    )
                ]
            )
            row_kinds.append("group")
            for violation in violations:
                matched = _take_recommendations_for(violation, pending)
                rows.append(
                    [
                        _fitting_card(
                            partial(_violation_card, violation, matched),
                            max_card_height,
                            fallback=partial(_oversized_violation_card, violation),
                        )
                    ]
                )
                row_kinds.append("card")
        if pending:
            rows.append(
                [Paragraph(f"OUTRAS RECOMENDAÇÕES ({len(pending)})", STYLES["group"])]
            )
            row_kinds.append("group")
            for rec in pending:
                rows.append(
                    [
                        _fitting_card(
                            partial(_recommendation_card, rec),
                            max_card_height,
                            fallback=partial(_oversized_recommendation_card, rec),
                        )
                    ]
                )
                row_kinds.append("card")

        table = Table(rows, colWidths=[CONTENT_WIDTH], repeatRows=1)
        table.setStyle(TableStyle(_entity_table_commands(row_kinds)))
        if len(rows) <= 4:
            return [KeepTogether([table])]
        return [table]


def _entity_notes(report: EntityReport, tz: tzinfo) -> list[str]:
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
    return notes


def _take_recommendations_for(
    violation: Violation, pending: list[Recommendation]
) -> list[Recommendation]:
    target = normalized_attribute_path(violation.attribute_path)
    matched = [rec for rec in pending if normalized_attribute_path(rec.attribute_path) == target]
    for rec in matched:
        pending.remove(rec)
    return matched


def _entity_table_commands(row_kinds: list[str]) -> list[tuple[Any, ...]]:
    commands: list[tuple[Any, ...]] = [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]
    for index, kind in enumerate(row_kinds):
        if kind == "intro":
            commands += [
                ("TOPPADDING", (0, index), (0, index), 4),
                ("BOTTOMPADDING", (0, index), (0, index), 2),
            ]
        elif kind == "group":
            commands += [
                ("TOPPADDING", (0, index), (0, index), 6),
                ("BOTTOMPADDING", (0, index), (0, index), 3),
            ]
        elif kind == "card":
            commands.append(("BOTTOMPADDING", (0, index), (0, index), 4))
    return commands


def _fitting_card(
    build: CardBuilder, max_height: float, *, fallback: Callable[[], Table]
) -> Table:
    for limit in (FIELD_MAX_CHARS, COMPACT_FIELD_MAX_CHARS):
        card = build(limit)
        _, height = card.wrap(CONTENT_WIDTH, max_height)
        if height <= max_height:
            return card
    return fallback()


def _tiles(
    tiles: list[tuple[str, str]],
    *,
    highlight_first: bool = False,
    severities: list[ViolationSeverity | None] | None = None,
) -> Table:
    width = CONTENT_WIDTH / len(tiles)
    table = Table(
        [
            [Paragraph(safe_text(value), STYLES["tile_value"]) for _, value in tiles],
            [Paragraph(safe_text(label), STYLES["tile_label"]) for label, _ in tiles],
        ],
        colWidths=[width] * len(tiles),
    )
    commands: list[tuple[Any, ...]] = [
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


def _badge_cell(severity: ViolationSeverity | None, level: str | None = None) -> list[Paragraph]:
    style = SEVERITY_STYLES[severity] if severity is not None else RECOMMENDATION_STYLE
    label = SEVERITY_BADGES[severity] if severity is not None else "SLM"
    cell = [Paragraph(f'<font color="{style.text_hex}">{label}</font>', STYLES["badge"])]
    if level:
        cell.append(
            Paragraph(f'<font color="{style.text_hex}">{level}</font>', STYLES["badge_level"])
        )
    return cell


def _entity_band(report: EntityReport) -> Table:
    band = Table(
        [
            [
                Paragraph(safe_text(report.entity_id, IDENTIFIER_MAX_CHARS), STYLES["entity_id"]),
                Paragraph(
                    f'<font color="#5B6270" name="Helvetica">Status:</font> '
                    f"{safe_text(_status_label(report))}",
                    STYLES["entity_status"],
                ),
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


def _violation_title(violation: Violation) -> Paragraph:
    return Paragraph(
        f"<b>{safe_text(violation.attribute_path, IDENTIFIER_MAX_CHARS)}</b> &nbsp;·&nbsp; "
        f"{safe_text(rule_label(violation.rule), IDENTIFIER_MAX_CHARS)}",
        STYLES["card_title"],
    )


def _violation_level(violation: Violation) -> str:
    return "Nível 1" if violation.detected_by == DetectionSource.STRUCTURAL else "Nível 2"


def _violation_card(
    violation: Violation, recommendations: list[Recommendation], limit: int
) -> Table:
    body: list[Flowable] = [
        _violation_title(violation),
        Spacer(1, 1 * mm),
        Paragraph(safe_text(violation.message, limit), STYLES["body"]),
        Spacer(1, 2 * mm),
        _found_expected(violation, limit),
    ]
    for rec in recommendations:
        body += [Spacer(1, 2 * mm), _fix_panel(rec, limit)]
    return _card(
        _badge_cell(violation.severity, _violation_level(violation)),
        body,
        SEVERITY_STYLES[violation.severity],
    )


def _oversized_violation_card(violation: Violation) -> Table:
    return _card(
        _badge_cell(violation.severity, _violation_level(violation)),
        [_violation_title(violation), Spacer(1, 1 * mm), _oversized_notice()],
        SEVERITY_STYLES[violation.severity],
    )


def _recommendation_title(rec: Recommendation) -> Paragraph:
    return Paragraph(
        f"<b>{safe_text(rec.attribute_path, IDENTIFIER_MAX_CHARS)}</b> &nbsp;·&nbsp; "
        "recomendação sem violação correspondente",
        STYLES["card_title"],
    )


def _recommendation_card(rec: Recommendation, limit: int) -> Table:
    body: list[Flowable] = [_recommendation_title(rec), Spacer(1, 2 * mm), _fix_panel(rec, limit)]
    return _card(_badge_cell(None, "Nível 2"), body, RECOMMENDATION_STYLE)


def _oversized_recommendation_card(rec: Recommendation) -> Table:
    return _card(
        _badge_cell(None, "Nível 2"),
        [_recommendation_title(rec), Spacer(1, 1 * mm), _oversized_notice()],
        RECOMMENDATION_STYLE,
    )


def _oversized_notice() -> Paragraph:
    return Paragraph(
        "O conteúdo deste item é grande demais para caber em uma página do PDF. "
        "Consulte o detalhe completo na tela de relatório.",
        STYLES["muted"],
    )


def _card(badge: list[Paragraph], body: list[Flowable], style: SeverityStyle) -> Table:
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


def _found_expected(violation: Violation, limit: int) -> Table:
    inner = CARD_BODY_WIDTH - 16
    table = Table(
        [
            [
                Paragraph("ENCONTRADO", STYLES["diff_label"]),
                Paragraph("ESPERADO", STYLES["diff_label"]),
            ],
            [
                Paragraph(safe_text(_missing_if_none(violation.found), limit), STYLES["diff_value"]),
                Paragraph(
                    safe_text(_missing_if_none(violation.expected), limit), STYLES["diff_value"]
                ),
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


def _fix_panel(rec: Recommendation, limit: int) -> Table:
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
            [
                Paragraph("Justificativa", STYLES["fix_label"]),
                Paragraph(safe_text(rec.rationale, limit), STYLES["fix_value"]),
            ],
            [
                Paragraph("Correção proposta", STYLES["fix_label"]),
                Paragraph(safe_text(patch, limit), STYLES["fix_code"]),
            ],
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


def _sorted_reports(run: AuditRun) -> list[EntityReport]:
    order = {status: index for index, status in enumerate(CONFORMANCE_PRINT_ORDER)}
    return sorted(run.reports, key=lambda r: (order.get(r.status, len(order)), r.entity_id))


def _status_label(report: EntityReport) -> str:
    return CONFORMANCE_LABELS.get(report.status, report.status.value)


def _schema_origin_text(report: EntityReport, tz: tzinfo) -> str:
    model = report.data_model
    model_text = (
        f"{safe_text(model.model_name, IDENTIFIER_MAX_CHARS)} "
        f"v{safe_text(model.version, IDENTIFIER_MAX_CHARS)}"
        if model
        else ""
    )
    if report.schema_origin is not None:
        when = _format_datetime(report.schema_origin.fetched_at, tz)
        if report.schema_origin.source == SchemaSource.LIVE:
            return f"Schema {model_text} obtido ao vivo em {when}."
        return (
            f"<b>Schema {model_text} obtido do cache em {when}</b> — o catálogo não respondeu "
            "durante a auditoria, por isso foi usada a última cópia salva."
        )
    if report.status == ConformanceStatus.NO_MODEL_FOUND:
        return (
            "Nenhum Smart Data Model corresponde a este tipo de entidade; "
            "a validação não foi executada."
        )
    if report.status == ConformanceStatus.SCHEMA_UNAVAILABLE:
        return (
            f"O schema {model_text} não pôde ser obtido (nem ao vivo, nem do cache); "
            "a validação não foi executada."
        )
    return "Origem do schema não registrada neste relatório."


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
