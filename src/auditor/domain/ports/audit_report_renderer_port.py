"""AuditReportRendererPort — issue #23 (exportar o relatorio em PDF).

A Application layer so' conhece este contrato: "transforme um AuditRun ja'
carregado em um documento". Qual biblioteca gera o arquivo (ReportLab hoje,
ver ADR-0021) e' detalhe de infraestrutura e pode ser trocado sem tocar no
use case nem no router.

`render()` e' sincrono de proposito: gerar um PDF e' trabalho de CPU, nao
de I/O. Quem chama (ExportAuditReportUseCase) e' que decide rodar isso fora
do event loop, para que um relatorio com centenas de entidades nao trave as
outras requisicoes da API.
"""

from __future__ import annotations

from datetime import tzinfo
from typing import Protocol

from auditor.domain.entities.audit_run import AuditRun


class AuditReportRendererPort(Protocol):
    media_type: str
    file_extension: str

    def render(self, run: AuditRun, *, display_timezone: tzinfo) -> bytes:
        """Gera o documento completo do relatorio. `display_timezone` e' o
        fuso em que as datas aparecem no documento (o do usuario que pediu
        a exportacao) — o dominio guarda tudo em UTC."""
        ...
