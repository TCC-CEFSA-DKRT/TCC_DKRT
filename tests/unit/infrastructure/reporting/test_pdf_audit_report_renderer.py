"""Issue #23 — PDF do relatorio de auditoria (ADR-0021).

Le o PDF gerado de volta com pypdf para verificar o que o criterio de aceite
pede: A4, acentos preservados, severidades distinguiveis em escala de cinza,
paginacao com cabecalho/rodape e um relatorio com 500+ entidades gerado sem
travar.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4

from auditor.domain.entities.audit_run import AuditRun, RunStatus
from auditor.domain.entities.entity_report import EntityReport, SchemaOrigin, SchemaSource
from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.reporting.pdf_audit_report_renderer import (
    SEVERITY_STYLES,
    PdfAuditReportRenderer,
)

_NOW = datetime(2026, 10, 24, 17, 5, tzinfo=timezone.utc)
_STREETLIGHT = EntityType("Streetlight")
_MODEL = DataModelRef(
    subject="dataModel.Streetlighting",
    model_name="Streetlight",
    version="0.1.1",
    schema_url="https://example.org/Streetlight/schema.json",
)


def _non_conformant(entity_id: str) -> EntityReport:
    return EntityReport(
        entity_id=entity_id,
        entity_type=_STREETLIGHT,
        data_model=_MODEL,
        status=ConformanceStatus.NON_CONFORMANT,
        violations=[
            Violation(
                attribute_path="status",
                severity=ViolationSeverity.ERROR,
                rule="enum_violation",
                expected="ok | defectiveLamp | brokenLantern",
                found="quebrado",
                message="O valor não está entre os permitidos pelo modelo.",
                detected_by=DetectionSource.STRUCTURAL,
            ),
            Violation(
                attribute_path="lampHeight",
                severity=ViolationSeverity.WARNING,
                rule="attribute_name_synonym",
                expected="lanternHeight",
                found="lampHeight",
                message="Sinônimo de 'lanternHeight'.",
                detected_by=DetectionSource.SEMANTIC,
            ),
            Violation(
                attribute_path="description",
                severity=ViolationSeverity.INFO,
                rule="generic_description",
                expected=None,
                found="poste",
                message="Descrição genérica.",
                detected_by=DetectionSource.SEMANTIC,
            ),
        ],
        recommendations=[
            Recommendation(
                attribute_path="status",
                action=RecommendationAction.FIX_FORMAT,
                proposed_patch={"attribute": "status", "value": "brokenLantern"},
                rationale="'quebrado' corresponde a uma luminária danificada.",
                confidence=0.82,
            )
        ],
        schema_origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=_NOW),
        semantic_analysis_skipped=False,
    )


def _run(reports: list[EntityReport], tenant: str = "openiot") -> AuditRun:
    run = AuditRun.create(
        tenant=Tenant(fiware_service=tenant, fiware_service_path="/"),
        entity_type=_STREETLIGHT,
        broker_url="http://orion:1026",
        started_at=_NOW - timedelta(minutes=3),
    )
    for report in reports:
        run.add_report(report)
    run.status = RunStatus.COMPLETED
    run.finished_at = _NOW
    return run


def _render(run: AuditRun, tz=timezone.utc) -> PdfReader:
    data = PdfAuditReportRenderer().render(run, display_timezone=tz)
    assert data.startswith(b"%PDF")
    return PdfReader(BytesIO(data))


def _text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() for page in reader.pages)


class TestDocumentLayout:
    def test_pages_are_a4_portrait(self):
        reader = _render(_run([_non_conformant("urn:1")]))

        box = reader.pages[0].mediabox
        assert round(float(box.width)) == round(A4[0])
        assert round(float(box.height)) == round(A4[1])

    def test_header_has_tenant_type_dates_and_aggregated_summary(self):
        conformant = EntityReport(
            entity_id="urn:2",
            entity_type=_STREETLIGHT,
            data_model=_MODEL,
            status=ConformanceStatus.CONFORMANT,
            violations=[],
            schema_origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=_NOW),
        )
        reader = _render(_run([_non_conformant("urn:1"), conformant]), tz=ZoneInfo("America/Sao_Paulo"))

        first_page = reader.pages[0].extract_text()
        assert "Relatório de auditoria de conformidade" in first_page
        assert "openiot" in first_page
        assert "Streetlight" in first_page
        # 17:05 UTC exibido no fuso de quem exportou (UTC-3)
        assert "24/10/2026 14:05" in first_page
        assert "Resumo" in first_page
        assert "1 (50%)" in first_page
        for label in ("Erros", "Avisos", "Informações", "Recomendações do SLM"):
            assert label in first_page

    def test_overview_lists_every_entity_with_the_ones_needing_fixes_first(self):
        conformant = EntityReport(
            entity_id="urn:a-conforme",
            entity_type=_STREETLIGHT,
            data_model=_MODEL,
            status=ConformanceStatus.CONFORMANT,
            violations=[],
            schema_origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=_NOW),
        )
        reader = _render(_run([conformant, _non_conformant("urn:z-nao-conforme")]))

        first_page = reader.pages[0].extract_text()
        assert "Visão geral das entidades" in first_page
        assert first_page.index("urn:z-nao-conforme") < first_page.index("urn:a-conforme")

    def test_detail_shows_attribute_rule_found_expected_and_the_fix(self):
        text = _text(_render(_run([_non_conformant("urn:1")])))

        assert "Valor fora da lista permitida" in text
        assert "ENCONTRADO" in text and "ESPERADO" in text
        assert "quebrado" in text
        assert "Como corrigir: Corrigir o formato" in text
        assert "Justificativa" in text and "Correção proposta" in text
        assert "brokenLantern" in text
        assert "obtido ao vivo em" in text

    def test_accents_are_preserved(self):
        text = _text(_render(_run([_non_conformant("urn:ação-çãé")])))

        assert "urn:ação-çãé" in text
        assert "Não conforme" in text
        assert "Informações" in text

    def test_characters_outside_the_pdf_fonts_do_not_break_generation(self):
        report = _non_conformant("urn:emoji-🚦")

        text = _text(_render(_run([report])))

        assert "urn:emoji-?" in text

    def test_run_without_entities_says_so(self):
        text = _text(_render(_run([])))

        assert "Esta auditoria não encontrou nenhuma entidade." in text

    def test_no_model_entity_explains_that_validation_did_not_run(self):
        no_model = EntityReport(
            entity_id="urn:3",
            entity_type=_STREETLIGHT,
            data_model=None,
            status=ConformanceStatus.NO_MODEL_FOUND,
            violations=[],
        )

        text = _text(_render(_run([no_model])))

        assert "Nenhum Smart Data Model corresponde a este tipo" in text
        assert "Nenhuma violação encontrada" not in text


class TestGrayscalePrinting:
    def test_severities_are_labelled_in_text_not_only_by_colour(self):
        text = _text(_render(_run([_non_conformant("urn:1")])))

        for label in ("ERRO", "AVISO", "INFO"):
            assert label in text

    def test_severity_fills_stay_distinct_in_grayscale(self):
        def luminance(color) -> float:
            return 0.2126 * color.red + 0.7152 * color.green + 0.0722 * color.blue

        levels = sorted(luminance(style.fill) for style in SEVERITY_STYLES.values())

        assert all(b - a >= 0.3 for a, b in zip(levels, levels[1:])), levels


class TestLargeReports:
    def test_500_plus_entities_paginate_with_header_and_page_numbers(self):
        reports = [_non_conformant(f"urn:ngsi-ld:Streetlight:{i:04d}") for i in range(520)]

        started = time.perf_counter()
        reader = _render(_run(reports))
        elapsed = time.perf_counter() - started

        total = len(reader.pages)
        assert total > 20
        last_page = reader.pages[-1].extract_text()
        assert f"Página {total} de {total}" in last_page
        assert "DKRT · Relatório de auditoria de conformidade" in last_page
        assert "urn:ngsi-ld:Streetlight:0519" in last_page
        # Limite folgado (a geracao leva alguns segundos numa maquina comum): serve so'
        # para pegar uma regressao grosseira, nunca para medir desempenho.
        assert elapsed < 60
