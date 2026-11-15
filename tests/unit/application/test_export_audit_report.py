from __future__ import annotations

import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from auditor.application.errors import AuditReportTooLargeError
from auditor.application.report_export import ReportExportLimits
from auditor.application.use_cases.export_audit_report import ExportAuditReportUseCase
from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.entities.entity_report import EntityReport
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant


class _FakeRenderer:
    media_type = "application/pdf"
    file_extension = "pdf"

    def __init__(self, content: bytes = b"%PDF-fake") -> None:
        self.content = content
        self.calls = 0
        self.thread_id: int | None = None
        self.timezone = None

    def render(self, run, *, display_timezone):
        self.calls += 1
        self.thread_id = threading.get_ident()
        self.timezone = display_timezone
        return self.content


_LIMITS = ReportExportLimits(max_entities=1000, max_bytes=700_000)


def _use_case(renderer: _FakeRenderer, limits: ReportExportLimits = _LIMITS):
    return ExportAuditReportUseCase(renderer, limits)


def _run(entity_type: str | None) -> AuditRun:
    return AuditRun.create(
        tenant=Tenant(fiware_service="openiot"),
        entity_type=EntityType(entity_type) if entity_type else None,
        broker_url="http://orion:1026",
        started_at=datetime(2026, 10, 24, 17, 5, tzinfo=timezone.utc),
    )


async def test_renders_outside_the_event_loop_thread():
    renderer = _FakeRenderer()

    report = await _use_case(renderer).execute(_run("Streetlight"), timezone.utc)

    assert report.content == b"%PDF-fake"
    assert report.media_type == "application/pdf"
    assert renderer.thread_id != threading.get_ident()


async def test_filename_uses_the_entity_type_and_the_local_start_time():
    tz = ZoneInfo("America/Sao_Paulo")

    report = await _use_case(_FakeRenderer()).execute(_run("Streetlight"), tz)

    assert report.filename == "relatorio-streetlight-2026-10-24-1405.pdf"


async def test_filename_for_a_run_over_all_types():
    report = await _use_case(_FakeRenderer()).execute(_run(None), timezone.utc)

    assert report.filename == "relatorio-todos-os-tipos-2026-10-24-1705.pdf"


def _run_with_entities(count: int) -> AuditRun:
    run = _run("Streetlight")
    for index in range(count):
        run.add_report(
            EntityReport(
                entity_id=f"urn:{index}",
                entity_type=EntityType("Streetlight"),
                data_model=None,
                status=ConformanceStatus.NO_MODEL_FOUND,
                violations=[],
            )
        )
    return run


async def test_too_many_entities_is_refused_before_rendering():
    renderer = _FakeRenderer()
    limits = ReportExportLimits(max_entities=3, max_bytes=700_000)

    with pytest.raises(AuditReportTooLargeError) as raised:
        await _use_case(renderer, limits).execute(_run_with_entities(4), timezone.utc)

    assert renderer.calls == 0
    assert raised.value.limit == 3
    assert raised.value.actual == 4
    assert "4 entidades" in str(raised.value)
    assert "limite para exportar em PDF é de 3" in str(raised.value)


async def test_entities_up_to_the_limit_are_exported():
    limits = ReportExportLimits(max_entities=3, max_bytes=700_000)

    report = await _use_case(_FakeRenderer(), limits).execute(_run_with_entities(3), timezone.utc)

    assert report.content == b"%PDF-fake"


async def test_a_document_bigger_than_the_limit_is_refused_with_its_size():
    renderer = _FakeRenderer(content=b"x" * 1_033_000)

    with pytest.raises(AuditReportTooLargeError) as raised:
        await _use_case(renderer).execute(_run("Streetlight"), timezone.utc)

    assert raised.value.actual == 1_033_000
    assert "1033 KB" in str(raised.value)
    assert "700 KB" in str(raised.value)
