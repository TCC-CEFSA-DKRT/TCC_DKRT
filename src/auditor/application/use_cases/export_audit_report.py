"""ExportAuditReportUseCase — issue #23 (exportar o relatorio em PDF).

Recebe um AuditRun ja' carregado (o router faz a leitura com o mesmo
isolamento de tenant de GET /audits/{run_id}) e devolve o documento pronto
para download. A geracao roda em uma thread separada (`asyncio.to_thread`):
um relatorio com 500+ entidades leva alguns segundos de CPU, e rodar isso no
event loop travaria todas as outras requisicoes da API nesse intervalo —
exatamente o que o criterio de aceite da #23 pede para evitar.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import tzinfo

from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.ports.audit_report_renderer_port import AuditReportRendererPort


@dataclass(frozen=True)
class ExportedReport:
    content: bytes
    media_type: str
    filename: str


class ExportAuditReportUseCase:
    def __init__(self, renderer: AuditReportRendererPort) -> None:
        self._renderer = renderer

    async def execute(self, run: AuditRun, display_timezone: tzinfo) -> ExportedReport:
        content = await asyncio.to_thread(
            self._renderer.render, run, display_timezone=display_timezone
        )
        return ExportedReport(
            content=content,
            media_type=self._renderer.media_type,
            filename=_filename_for(run, display_timezone, self._renderer.file_extension),
        )


def _filename_for(run: AuditRun, display_timezone: tzinfo, extension: str) -> str:
    """Ex.: relatorio-streetlight-2026-10-24-1405.pdf — so' ASCII, para o
    nome sair igual em qualquer navegador/sistema operacional."""
    entity_type = run.entity_type.value if run.entity_type else "todos-os-tipos"
    slug = re.sub(r"[^a-z0-9]+", "-", entity_type.lower()).strip("-") or "relatorio"
    started = run.started_at.astimezone(display_timezone).strftime("%Y-%m-%d-%H%M")
    return f"relatorio-{slug}-{started}.{extension}"
