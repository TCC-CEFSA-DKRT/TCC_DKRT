from __future__ import annotations

import asyncio
import re
from datetime import tzinfo

from auditor.application.errors import AuditReportTooLargeError
from auditor.application.report_export import ExportedReport, ReportExportLimits
from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.ports.audit_report_renderer_port import AuditReportRendererPort


class ExportAuditReportUseCase:
    def __init__(self, renderer: AuditReportRendererPort, limits: ReportExportLimits) -> None:
        self._renderer = renderer
        self._limits = limits

    async def execute(self, run: AuditRun, display_timezone: tzinfo) -> ExportedReport:
        entities = len(run.reports)
        if entities > self._limits.max_entities:
            raise AuditReportTooLargeError.too_many_entities(
                limit=self._limits.max_entities, actual=entities
            )
        content = await asyncio.to_thread(
            self._renderer.render, run, display_timezone=display_timezone
        )
        if len(content) > self._limits.max_bytes:
            raise AuditReportTooLargeError.document_too_big(
                limit=self._limits.max_bytes, actual=len(content)
            )
        return ExportedReport(
            content=content,
            media_type=self._renderer.media_type,
            filename=_filename_for(run, display_timezone, self._renderer.file_extension),
        )


def _filename_for(run: AuditRun, display_timezone: tzinfo, extension: str) -> str:
    entity_type = run.entity_type.value if run.entity_type else "todos-os-tipos"
    slug = re.sub(r"[^a-z0-9]+", "-", entity_type.lower()).strip("-") or "relatorio"
    started = run.started_at.astimezone(display_timezone).strftime("%Y-%m-%d-%H%M")
    return f"relatorio-{slug}-{started}.{extension}"
