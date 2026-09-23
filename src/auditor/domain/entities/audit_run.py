"""AuditRun aggregate — ver .cursor/specs/fase1.spec.md, secao 2.4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from auditor.domain.entities.entity_report import EntityReport
from auditor.domain.errors import InvariantViolationError
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class RunSummary:
    """Contadores agregados de um AuditRun. Sempre derivados de `reports` —
    nunca mutados de forma independente (ver AuditRun.add_report).

    Ajuste retroativo (Fase 3, ao desenhar a persistencia dos contadores):
    a Fase 2 introduziu ConformanceStatus.SCHEMA_UNAVAILABLE, mas este
    agregado nunca foi atualizado para contabiliza-lo — um EntityReport com
    esse status derrubava o invariante abaixo (total_entities contava o
    report, mas nenhum dos quatro contadores originais o somava). Corrigido
    adicionando schema_unavailable_count, mesmo padrao dos demais.
    """

    total_entities: int
    conformant_count: int
    non_conformant_count: int
    partial_count: int
    no_model_count: int
    schema_unavailable_count: int

    def __post_init__(self) -> None:
        counted = (
            self.conformant_count
            + self.non_conformant_count
            + self.partial_count
            + self.no_model_count
            + self.schema_unavailable_count
        )
        if counted != self.total_entities:
            raise InvariantViolationError(
                f"Contadores de RunSummary somam {counted}, esperado "
                f"total_entities={self.total_entities}."
            )

    @classmethod
    def empty(cls) -> "RunSummary":
        return cls(0, 0, 0, 0, 0, 0)

    @classmethod
    def from_reports(cls, reports: list[EntityReport]) -> "RunSummary":
        counts = {status: 0 for status in ConformanceStatus}
        for report in reports:
            counts[report.status] += 1
        return cls(
            total_entities=len(reports),
            conformant_count=counts[ConformanceStatus.CONFORMANT],
            non_conformant_count=counts[ConformanceStatus.NON_CONFORMANT],
            partial_count=counts[ConformanceStatus.PARTIAL],
            no_model_count=counts[ConformanceStatus.NO_MODEL_FOUND],
            schema_unavailable_count=counts[ConformanceStatus.SCHEMA_UNAVAILABLE],
        )


@dataclass
class AuditRun:
    """Agregado raiz de uma execucao de auditoria."""

    id: UUID
    tenant: Tenant
    entity_type: EntityType | None
    status: RunStatus
    reports: list[EntityReport]
    summary: RunSummary
    started_at: datetime
    finished_at: datetime | None
    broker_url: str
    # Fase 5 (progresso, .cursor/specs/fase5.spec.md secao 4): quantas
    # entidades o Orion devolveu para este run — conhecido so' depois que
    # fetch_entities() retorna, por isso comeca None (nunca 0 inventado,
    # que seria indistinguivel de uma auditoria vazia de verdade).
    total_entities_discovered: int | None = None
    # Fase 5 (worker, secao 3.1): motivo textual quando status=FAILED —
    # ex. "context_broker_unavailable", "max_retries_exceeded". None para
    # qualquer outro status.
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status == RunStatus.COMPLETED and self.finished_at is None:
            raise InvariantViolationError(
                "AuditRun.finished_at nao pode ser None quando status e COMPLETED."
            )

    @classmethod
    def create(
        cls,
        tenant: Tenant,
        entity_type: EntityType | None,
        broker_url: str,
        *,
        run_id: UUID | None = None,
        started_at: datetime | None = None,
    ) -> "AuditRun":
        """Factory para um run recem-criado — ainda sem relatorios."""
        return cls(
            id=run_id or uuid4(),
            tenant=tenant,
            entity_type=entity_type,
            status=RunStatus.QUEUED,
            reports=[],
            summary=RunSummary.empty(),
            started_at=started_at or datetime.now(timezone.utc),
            finished_at=None,
            broker_url=broker_url,
        )

    def add_report(self, report: EntityReport) -> None:
        """Adiciona um relatorio e recalcula `summary` — quem chama nunca
        precisa manter o agregado sincronizado manualmente."""
        self.reports.append(report)
        self.summary = RunSummary.from_reports(self.reports)
