"""AuditRepositoryPort — ver .cursor/specs/fase3.spec.md.

Escrita incremental por desenho (secao 1): `create_run` no inicio,
`append_report` uma vez por entidade processada — nao um `save(run)` unico no
fim. Isso evita usar memoria proporcional ao tamanho do run e nao perde
progresso se o worker cair no meio (Fase 5).

Requisito de seguranca verificavel por maquina (secao 4): todo metodo de
LEITURA recebe `tenant` como parametro obrigatorio — ver
tests/unit/domain/ports/test_audit_repository_port_signatures.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Protocol, TypeVar
from uuid import UUID

from auditor.domain.entities.audit_run import AuditRun, RunStatus, RunSummary
from auditor.domain.entities.entity_report import EntityReport
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant


@dataclass(frozen=True)
class RunFilters:
    entity_type: EntityType | None = None
    status: RunStatus | None = None
    started_after: datetime | None = None
    started_before: datetime | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class AuditRunSummaryView:
    """Visao leve de um AuditRun para listagens — sem os relatorios
    completos (isso e' o que `get_by_id` reconstroi, para leitura pontual)."""

    id: UUID
    tenant: Tenant
    entity_type: EntityType | None
    status: RunStatus
    summary: RunSummary
    started_at: datetime
    finished_at: datetime | None
    broker_url: str
    total_entities_discovered: int | None = None
    failure_reason: str | None = None


T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total


class AuditRepositoryPort(Protocol):
    async def create_run(self, run: AuditRun) -> None:
        """Grava o run no estado inicial (QUEUED, sem relatorios ainda). Nao
        recebe `tenant` separado — `run.tenant` ja carrega essa informacao."""
        ...

    async def append_report(self, run_id: UUID, tenant: Tenant, report: EntityReport) -> None:
        """Adiciona um relatorio de entidade a um run existente. Idempotente
        por (run_id, entity_id): reentrega do mesmo relatorio (Fase 5,
        reprocessamento de job) substitui, nunca duplica. Levanta
        `RunNotFoundError` se o run nao existe (ou nao e do tenant)."""
        ...

    async def update_run_status(
        self,
        run_id: UUID,
        tenant: Tenant,
        status: RunStatus,
        finished_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> None: ...

    async def set_total_entities(self, run_id: UUID, tenant: Tenant, total: int) -> None:
        """Registra quantas entidades o broker devolveu para este run — uma
        vez, logo apos fetch_entities() retornar (Fase 5, secao 4). Antes
        disso o valor fica None (nunca 0 inventado)."""
        ...

    async def count_reports(self, run_id: UUID, tenant: Tenant) -> int:
        """COUNT direto no banco (nao um valor em memoria do worker) — a
        fonte de verdade do progresso precisa ser a mesma para qualquer
        consumidor da API, nao o processo de um worker especifico
        (Fase 5, secao 4.2)."""
        ...

    async def get_by_id(self, run_id: UUID, tenant: Tenant) -> AuditRun | None:
        """Reconstroi o agregado completo — usado para leitura pontual (nao
        durante o processamento). `None` se o run nao existe OU pertence a
        outro tenant — as duas situacoes sao indistinguiveis de fora."""
        ...

    async def list_runs(self, tenant: Tenant, filters: RunFilters) -> Page[AuditRunSummaryView]: ...

    async def list_run_summaries_over_time(
        self, tenant: Tenant, entity_type: EntityType
    ) -> list[AuditRunSummaryView]:
        """Resumos ordenados cronologicamente — dado bruto para a tela de
        evolucao de conformidade no tempo (frontend, Fase 8)."""
        ...
