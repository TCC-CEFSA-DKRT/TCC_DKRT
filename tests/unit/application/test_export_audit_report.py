"""Issue #23 — ExportAuditReportUseCase."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auditor.application.use_cases.export_audit_report import ExportAuditReportUseCase
from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant


class _FakeRenderer:
    media_type = "application/pdf"
    file_extension = "pdf"

    def __init__(self) -> None:
        self.thread_id: int | None = None
        self.timezone = None

    def render(self, run, *, display_timezone):
        self.thread_id = threading.get_ident()
        self.timezone = display_timezone
        return b"%PDF-fake"


def _run(entity_type: str | None) -> AuditRun:
    return AuditRun.create(
        tenant=Tenant(fiware_service="openiot"),
        entity_type=EntityType(entity_type) if entity_type else None,
        broker_url="http://orion:1026",
        started_at=datetime(2026, 10, 24, 17, 5, tzinfo=timezone.utc),
    )


async def test_renders_outside_the_event_loop_thread():
    renderer = _FakeRenderer()

    report = await ExportAuditReportUseCase(renderer).execute(_run("Streetlight"), timezone.utc)

    assert report.content == b"%PDF-fake"
    assert report.media_type == "application/pdf"
    assert renderer.thread_id != threading.get_ident()


async def test_filename_uses_the_entity_type_and_the_local_start_time():
    tz = ZoneInfo("America/Sao_Paulo")

    report = await ExportAuditReportUseCase(_FakeRenderer()).execute(_run("Streetlight"), tz)

    assert report.filename == "relatorio-streetlight-2026-10-24-1405.pdf"


async def test_filename_for_a_run_over_all_types():
    report = await ExportAuditReportUseCase(_FakeRenderer()).execute(_run(None), timezone.utc)

    assert report.filename == "relatorio-todos-os-tipos-2026-10-24-1705.pdf"
