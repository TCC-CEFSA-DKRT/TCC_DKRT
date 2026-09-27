"""PostgresAuditRepository — implementa AuditRepositoryPort. Ver
.cursor/specs/fase3.spec.md.

Recebe uma `AsyncConnection` ja aberta (nunca um `Engine`) — de proposito:
quem possui o ciclo de vida da transacao e' o `SqlAlchemyUnitOfWork` (secao
7), nao o repository. E' isso que torna "chame append_report varias vezes e
so commite no fim, ou reverta tudo se algo falhar no meio" possivel — cada
metodo aqui e' so uma serie de `execute()` na conexao que recebeu, sem abrir
nem fechar transacao por conta propria.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from auditor.domain.entities.audit_run import AuditRun, RunStatus
from auditor.domain.entities.entity_report import EntityReport
from auditor.domain.errors import InvariantViolationError, RunNotFoundError
from auditor.domain.ports.audit_repository_port import AuditRunSummaryView, Page, RunFilters
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.persistence.mappers import (
    audit_run_to_row,
    entity_report_to_rows,
    row_to_audit_run,
    row_to_audit_run_summary_view,
    row_to_entity_report,
)
from auditor.infrastructure.persistence.tables import (
    audit_runs_table,
    entity_reports_table,
    recommendations_table,
    violations_table,
)

_STATUS_COLUMN = {
    ConformanceStatus.CONFORMANT: "conformant_count",
    ConformanceStatus.NON_CONFORMANT: "non_conformant_count",
    ConformanceStatus.PARTIAL: "partial_count",
    ConformanceStatus.NO_MODEL_FOUND: "no_model_count",
    ConformanceStatus.SCHEMA_UNAVAILABLE: "schema_unavailable_count",
}


class PostgresAuditRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._conn = connection

    async def create_run(self, run: AuditRun) -> None:
        await self._conn.execute(insert(audit_runs_table).values(**audit_run_to_row(run)))

    async def append_report(self, run_id: UUID, tenant: Tenant, report: EntityReport) -> None:
        run_row = (
            await self._conn.execute(
                select(audit_runs_table.c.id).where(
                    audit_runs_table.c.id == run_id,
                    audit_runs_table.c.tenant_fiware_service == tenant.fiware_service,
                    audit_runs_table.c.tenant_fiware_service_path == tenant.fiware_service_path,
                )
            )
        ).first()
        if run_row is None:
            raise RunNotFoundError(f"AuditRun {run_id} nao encontrado para o tenant informado.")

        # SELECT ... FOR UPDATE: trava a linha (se existir) dentro desta
        # transacao — e' o que garante que o reprocessamento sequencial de um
        # run (Fase 5, mesmo job reentregue) nao corrompa os contadores.
        existing = (
            await self._conn.execute(
                select(entity_reports_table.c.id, entity_reports_table.c.status)
                .where(
                    entity_reports_table.c.run_id == run_id,
                    entity_reports_table.c.entity_id == report.entity_id,
                )
                .with_for_update()
            )
        ).first()

        payload = entity_report_to_rows(
            run_id, report, report_id=existing.id if existing is not None else None
        )

        delta_total = 0
        increment_column: str | None = None

        if existing is None:
            # primeira vez que esta entidade aparece neste run
            await self._conn.execute(insert(entity_reports_table).values(**payload["report"]))
            delta_total = 1
            increment_column = _STATUS_COLUMN[report.status]
        else:
            # reentrega/reprocessamento: substitui o conteudo, nunca duplica
            await self._conn.execute(
                delete(violations_table).where(violations_table.c.report_id == existing.id)
            )
            await self._conn.execute(
                delete(recommendations_table).where(recommendations_table.c.report_id == existing.id)
            )
            await self._conn.execute(
                update(entity_reports_table)
                .where(entity_reports_table.c.id == existing.id)
                .values(**{k: v for k, v in payload["report"].items() if k != "id"})
            )
            old_status = ConformanceStatus(existing.status)
            if old_status != report.status:
                # validacao estrutural e' funcao pura — na pratica isso nao
                # deveria acontecer (mesma entidade + mesmo schema = mesmo
                # resultado), mas se acontecer, a contagem nao pode ficar
                # errada por isso.
                old_column = _STATUS_COLUMN[old_status]
                await self._conn.execute(
                    update(audit_runs_table)
                    .where(audit_runs_table.c.id == run_id)
                    .values(**{old_column: audit_runs_table.c[old_column] - 1})
                )
                increment_column = _STATUS_COLUMN[report.status]

        if payload["violations"]:
            await self._conn.execute(insert(violations_table), payload["violations"])
        if payload["recommendations"]:
            await self._conn.execute(insert(recommendations_table), payload["recommendations"])

        update_values: dict[str, object] = {}
        if delta_total:
            update_values["total_entities"] = audit_runs_table.c.total_entities + delta_total
        if increment_column:
            update_values[increment_column] = audit_runs_table.c[increment_column] + 1
        if update_values:
            await self._conn.execute(
                update(audit_runs_table).where(audit_runs_table.c.id == run_id).values(**update_values)
            )

    async def update_run_status(
        self,
        run_id: UUID,
        tenant: Tenant,
        status: RunStatus,
        finished_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> None:
        if status == RunStatus.COMPLETED and finished_at is None:
            raise InvariantViolationError(
                "update_run_status: finished_at nao pode ser None quando status e COMPLETED "
                "(mesmo invariante ja imposto pelo dominio em AuditRun)."
            )
        result = await self._conn.execute(
            update(audit_runs_table)
            .where(
                audit_runs_table.c.id == run_id,
                audit_runs_table.c.tenant_fiware_service == tenant.fiware_service,
                audit_runs_table.c.tenant_fiware_service_path == tenant.fiware_service_path,
            )
            .values(status=status.value, finished_at=finished_at, failure_reason=failure_reason)
        )
        if result.rowcount == 0:
            raise RunNotFoundError(f"AuditRun {run_id} nao encontrado para o tenant informado.")

    async def set_total_entities(self, run_id: UUID, tenant: Tenant, total: int) -> None:
        result = await self._conn.execute(
            update(audit_runs_table)
            .where(
                audit_runs_table.c.id == run_id,
                audit_runs_table.c.tenant_fiware_service == tenant.fiware_service,
                audit_runs_table.c.tenant_fiware_service_path == tenant.fiware_service_path,
            )
            .values(total_entities_discovered=total)
        )
        if result.rowcount == 0:
            raise RunNotFoundError(f"AuditRun {run_id} nao encontrado para o tenant informado.")

    async def count_reports(self, run_id: UUID, tenant: Tenant) -> int:
        # JOIN com audit_runs so' para confirmar que o run e' deste tenant —
        # nunca conta relatorios de um run que nao pertence a quem pergunta.
        run_exists = (
            await self._conn.execute(
                select(audit_runs_table.c.id).where(
                    audit_runs_table.c.id == run_id,
                    audit_runs_table.c.tenant_fiware_service == tenant.fiware_service,
                    audit_runs_table.c.tenant_fiware_service_path == tenant.fiware_service_path,
                )
            )
        ).first()
        if run_exists is None:
            raise RunNotFoundError(f"AuditRun {run_id} nao encontrado para o tenant informado.")

        return (
            await self._conn.execute(
                select(func.count()).select_from(entity_reports_table).where(
                    entity_reports_table.c.run_id == run_id
                )
            )
        ).scalar_one()

    async def get_by_id(self, run_id: UUID, tenant: Tenant) -> AuditRun | None:
        run_row = (
            await self._conn.execute(
                select(audit_runs_table).where(
                    audit_runs_table.c.id == run_id,
                    audit_runs_table.c.tenant_fiware_service == tenant.fiware_service,
                    audit_runs_table.c.tenant_fiware_service_path == tenant.fiware_service_path,
                )
            )
        ).mappings().first()
        if run_row is None:
            return None

        report_rows = (
            await self._conn.execute(
                select(entity_reports_table).where(entity_reports_table.c.run_id == run_id)
            )
        ).mappings().all()

        reports = []
        for report_row in report_rows:
            violation_rows = (
                await self._conn.execute(
                    select(violations_table).where(violations_table.c.report_id == report_row["id"])
                )
            ).mappings().all()
            recommendation_rows = (
                await self._conn.execute(
                    select(recommendations_table).where(
                        recommendations_table.c.report_id == report_row["id"]
                    )
                )
            ).mappings().all()
            reports.append(
                row_to_entity_report(dict(report_row), list(violation_rows), list(recommendation_rows))
            )

        return row_to_audit_run(dict(run_row), reports=reports)

    async def list_runs(self, tenant: Tenant, filters: RunFilters) -> Page[AuditRunSummaryView]:
        conditions = [
            audit_runs_table.c.tenant_fiware_service == tenant.fiware_service,
            audit_runs_table.c.tenant_fiware_service_path == tenant.fiware_service_path,
        ]
        if filters.entity_type is not None:
            conditions.append(audit_runs_table.c.entity_type == filters.entity_type.value)
        if filters.status is not None:
            conditions.append(audit_runs_table.c.status == filters.status.value)
        if filters.started_after is not None:
            conditions.append(audit_runs_table.c.started_at >= filters.started_after)
        if filters.started_before is not None:
            conditions.append(audit_runs_table.c.started_at <= filters.started_before)

        total = (
            await self._conn.execute(
                select(func.count()).select_from(audit_runs_table).where(*conditions)
            )
        ).scalar_one()

        rows = (
            await self._conn.execute(
                select(audit_runs_table)
                .where(*conditions)
                .order_by(audit_runs_table.c.started_at.desc())
                .limit(filters.page_size)
                .offset((filters.page - 1) * filters.page_size)
            )
        ).mappings().all()

        items = [row_to_audit_run_summary_view(dict(row)) for row in rows]
        return Page(items=items, page=filters.page, page_size=filters.page_size, total=total)

    async def list_run_summaries_over_time(
        self, tenant: Tenant, entity_type: EntityType
    ) -> list[AuditRunSummaryView]:
        rows = (
            await self._conn.execute(
                select(audit_runs_table)
                .where(
                    audit_runs_table.c.tenant_fiware_service == tenant.fiware_service,
                    audit_runs_table.c.tenant_fiware_service_path == tenant.fiware_service_path,
                    audit_runs_table.c.entity_type == entity_type.value,
                )
                .order_by(audit_runs_table.c.started_at.asc())
            )
        ).mappings().all()
        return [row_to_audit_run_summary_view(dict(row)) for row in rows]
