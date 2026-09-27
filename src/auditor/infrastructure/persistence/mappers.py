"""Mapeamento puro dominio <-> linhas de tabela (dicts). Ver
.cursor/specs/fase3.spec.md, secao 8.

Deliberadamente sem SQLAlchemy nem I/O aqui — so dicts e tipos de dominio.
Isso permite testar a traducao (a parte mais facil de errar de um
Repository) sem precisar de Postgres — ver
tests/unit/infrastructure/persistence/test_mappers.py. O
`PostgresAuditRepository` e' quem liga estas funcoes a consultas reais.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from auditor.domain.entities.audit_run import AuditRun, RunStatus, RunSummary
from auditor.domain.entities.entity_report import (
    EntityReport,
    InferenceBackend,
    SchemaOrigin,
    SchemaSource,
    SemanticAnalysisUsage,
)
from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import (
    DetectionSource,
    Violation,
    ViolationSeverity,
)
from auditor.domain.ports.audit_repository_port import AuditRunSummaryView
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant


def audit_run_to_row(run: AuditRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "tenant_fiware_service": run.tenant.fiware_service,
        "tenant_fiware_service_path": run.tenant.fiware_service_path,
        "entity_type": run.entity_type.value if run.entity_type else None,
        "status": run.status.value,
        "total_entities": run.summary.total_entities,
        "conformant_count": run.summary.conformant_count,
        "non_conformant_count": run.summary.non_conformant_count,
        "partial_count": run.summary.partial_count,
        "no_model_count": run.summary.no_model_count,
        "schema_unavailable_count": run.summary.schema_unavailable_count,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "broker_url": run.broker_url,
        "total_entities_discovered": run.total_entities_discovered,
        "failure_reason": run.failure_reason,
    }


def row_to_audit_run(row: dict[str, Any], reports: list[EntityReport]) -> AuditRun:
    return AuditRun(
        id=row["id"],
        tenant=Tenant(
            fiware_service=row["tenant_fiware_service"],
            fiware_service_path=row["tenant_fiware_service_path"],
        ),
        entity_type=EntityType(row["entity_type"]) if row["entity_type"] else None,
        status=RunStatus(row["status"]),
        reports=reports,
        summary=RunSummary(
            total_entities=row["total_entities"],
            conformant_count=row["conformant_count"],
            non_conformant_count=row["non_conformant_count"],
            partial_count=row["partial_count"],
            no_model_count=row["no_model_count"],
            schema_unavailable_count=row["schema_unavailable_count"],
        ),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        broker_url=row["broker_url"],
        total_entities_discovered=row.get("total_entities_discovered"),
        failure_reason=row.get("failure_reason"),
    )


def row_to_audit_run_summary_view(row: dict[str, Any]) -> AuditRunSummaryView:
    return AuditRunSummaryView(
        id=row["id"],
        tenant=Tenant(
            fiware_service=row["tenant_fiware_service"],
            fiware_service_path=row["tenant_fiware_service_path"],
        ),
        entity_type=EntityType(row["entity_type"]) if row["entity_type"] else None,
        status=RunStatus(row["status"]),
        summary=RunSummary(
            total_entities=row["total_entities"],
            conformant_count=row["conformant_count"],
            non_conformant_count=row["non_conformant_count"],
            partial_count=row["partial_count"],
            no_model_count=row["no_model_count"],
            schema_unavailable_count=row["schema_unavailable_count"],
        ),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        broker_url=row["broker_url"],
        total_entities_discovered=row.get("total_entities_discovered"),
        failure_reason=row.get("failure_reason"),
    )


def entity_report_to_rows(
    run_id: UUID, report: EntityReport, *, report_id: UUID | None = None
) -> dict[str, Any]:
    """Retorna a linha de entity_reports mais as listas de linhas de
    violations/recommendations associadas — tudo pronto pra inserir.

    `report_id` e' passado pelo Repository quando o relatorio ja existia
    (upsert por (run_id, entity_id) — idempotencia, secao 2 do spec) — assim
    o id nao muda entre duas gravacoes da mesma entidade no mesmo run.
    """
    rid = report_id or uuid4()

    report_row = {
        "id": rid,
        "run_id": run_id,
        "entity_id": report.entity_id,
        "entity_type": report.entity_type.value,
        "data_model_subject": report.data_model.subject if report.data_model else None,
        "data_model_name": report.data_model.model_name if report.data_model else None,
        "data_model_version": report.data_model.version if report.data_model else None,
        "data_model_schema_url": report.data_model.schema_url if report.data_model else None,
        "status": report.status.value,
        "schema_origin_source": report.schema_origin.source.value if report.schema_origin else None,
        "schema_origin_fetched_at": (
            report.schema_origin.fetched_at if report.schema_origin else None
        ),
        "semantic_analysis_skipped": report.semantic_analysis_skipped,
        "analyzed_at": report.analyzed_at,
        "processing_duration_seconds": report.processing_duration_seconds,
        "semantic_analysis_backend": (
            report.semantic_analysis_usage.backend.value
            if report.semantic_analysis_usage
            else None
        ),
        "semantic_analysis_compute_seconds": (
            report.semantic_analysis_usage.compute_seconds
            if report.semantic_analysis_usage
            else None
        ),
        "semantic_analysis_prompt_tokens": (
            report.semantic_analysis_usage.prompt_tokens
            if report.semantic_analysis_usage
            else None
        ),
        "semantic_analysis_completion_tokens": (
            report.semantic_analysis_usage.completion_tokens
            if report.semantic_analysis_usage
            else None
        ),
    }
    violation_rows = [
        {
            "id": uuid4(),
            "report_id": rid,
            "attribute_path": v.attribute_path,
            "severity": v.severity.value,
            "rule": v.rule,
            "expected": v.expected,
            "found": v.found,
            "message": v.message,
            "detected_by": v.detected_by.value,
        }
        for v in report.violations
    ]
    recommendation_rows = [
        {
            "id": uuid4(),
            "report_id": rid,
            "attribute_path": r.attribute_path,
            "action": r.action.value,
            "proposed_patch": r.proposed_patch,
            "rationale": r.rationale,
            "confidence": r.confidence,
            "applied": False,
        }
        for r in report.recommendations
    ]
    return {"report": report_row, "violations": violation_rows, "recommendations": recommendation_rows}


def row_to_entity_report(
    report_row: dict[str, Any],
    violation_rows: list[dict[str, Any]],
    recommendation_rows: list[dict[str, Any]],
) -> EntityReport:
    data_model = None
    if report_row["data_model_subject"] is not None:
        data_model = DataModelRef(
            subject=report_row["data_model_subject"],
            model_name=report_row["data_model_name"],
            version=report_row["data_model_version"],
            schema_url=report_row["data_model_schema_url"],
        )
    schema_origin = None
    if report_row["schema_origin_source"] is not None:
        schema_origin = SchemaOrigin(
            source=SchemaSource(report_row["schema_origin_source"]),
            fetched_at=report_row["schema_origin_fetched_at"],
        )
    semantic_analysis_usage = None
    if report_row.get("semantic_analysis_backend") is not None:
        semantic_analysis_usage = SemanticAnalysisUsage(
            backend=InferenceBackend(report_row["semantic_analysis_backend"]),
            compute_seconds=report_row.get("semantic_analysis_compute_seconds"),
            prompt_tokens=report_row.get("semantic_analysis_prompt_tokens"),
            completion_tokens=report_row.get("semantic_analysis_completion_tokens"),
        )
    violations = [
        Violation(
            attribute_path=row["attribute_path"],
            severity=ViolationSeverity(row["severity"]),
            rule=row["rule"],
            expected=row["expected"],
            found=row["found"],
            message=row["message"],
            detected_by=DetectionSource(row["detected_by"]),
        )
        for row in violation_rows
    ]
    recommendations = [
        Recommendation(
            attribute_path=row["attribute_path"],
            action=RecommendationAction(row["action"]),
            proposed_patch=row["proposed_patch"],
            rationale=row["rationale"],
            confidence=row["confidence"],
        )
        for row in recommendation_rows
    ]
    return EntityReport(
        entity_id=report_row["entity_id"],
        entity_type=EntityType(report_row["entity_type"]),
        data_model=data_model,
        status=ConformanceStatus(report_row["status"]),
        violations=violations,
        recommendations=recommendations,
        schema_origin=schema_origin,
        semantic_analysis_skipped=report_row["semantic_analysis_skipped"],
        analyzed_at=report_row["analyzed_at"],
        processing_duration_seconds=report_row.get("processing_duration_seconds"),
        semantic_analysis_usage=semantic_analysis_usage,
    )
