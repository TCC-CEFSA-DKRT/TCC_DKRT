from __future__ import annotations

from datetime import tzinfo
from typing import Protocol

from auditor.domain.entities.audit_run import AuditRun


class AuditReportRendererPort(Protocol):
    media_type: str
    file_extension: str

    def render(self, run: AuditRun, *, display_timezone: tzinfo) -> bytes: ...
