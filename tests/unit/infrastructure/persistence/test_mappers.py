"""Fase 3 — mapeamento puro dominio <-> linhas. Ver .cursor/specs/fase3.spec.md,
secao 8.

Sem banco: testa so a traducao. A persistencia de fato (tipos SQL nativos,
transacao, constraints) e' testada em isolado com Postgres real, em
tests/integration/persistence/.
"""

from datetime import datetime, timezone
from uuid import uuid4

from auditor.domain.entities.audit_run import AuditRun, RunStatus
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
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.persistence.mappers import (
    audit_run_to_row,
    entity_report_to_rows,
    row_to_audit_run,
    row_to_audit_run_summary_view,
    row_to_entity_report,
)

_DATA_MODEL = DataModelRef(
    subject="dataModel.Streetlighting",
    model_name="Streetlight",
    version="latest",
    schema_url="https://example.org/schema.json",
)


def _full_report(entity_id: str) -> EntityReport:
    return EntityReport(
        entity_id=entity_id,
        entity_type=EntityType("Streetlight"),
        data_model=_DATA_MODEL,
        status=ConformanceStatus.PARTIAL,
        violations=[
            Violation(
                attribute_path="temp",
                severity=ViolationSeverity.WARNING,
                rule="unexpected_property",
                expected=None,
                found="temp",
                message="Atributo fora do schema.",
                detected_by=DetectionSource.STRUCTURAL,
            )
        ],
        recommendations=[
            Recommendation(
                attribute_path="temp",
                action=RecommendationAction.RENAME_ATTRIBUTE,
                proposed_patch={"from": "temp", "to": "temperature"},
                rationale="Sinonimo comum.",
                confidence=0.9,
            )
        ],
        schema_origin=SchemaOrigin(
            source=SchemaSource.CACHE, fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        ),
        semantic_analysis_skipped=False,
        analyzed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        # Fase 10 (.cursor/specs/fase10.spec.md, secao 3.3/3.4): valores
        # nao-None aqui garantem que os round-trips abaixo exercitam as
        # 5 colunas novas, nao so' o caso None default.
        processing_duration_seconds=2.5,
        semantic_analysis_usage=SemanticAnalysisUsage(
            backend=InferenceBackend.OLLAMA, compute_seconds=1.23
        ),
    )


class TestEntityReportRoundTrip:
    def test_report_with_violations_and_recommendations_round_trips(self):
        run_id = uuid4()
        original = _full_report("urn:ngsi-ld:Streetlight:001")

        payload = entity_report_to_rows(run_id, original)
        restored = row_to_entity_report(
            payload["report"], payload["violations"], payload["recommendations"]
        )

        assert restored == original

    def test_report_without_data_model_or_schema_origin_round_trips(self):
        original = EntityReport(
            entity_id="urn:ngsi-ld:Streetlight:002",
            entity_type=EntityType("Streetlight"),
            data_model=None,
            status=ConformanceStatus.NO_MODEL_FOUND,
            violations=[],
        )

        payload = entity_report_to_rows(uuid4(), original)
        restored = row_to_entity_report(
            payload["report"], payload["violations"], payload["recommendations"]
        )

        assert restored == original

    def test_report_with_bedrock_shaped_usage_round_trips(self):
        # Bedrock preenche prompt/completion tokens e deixa compute_seconds
        # None (o inverso do Ollama, ja coberto por _full_report acima) —
        # garante que a reconstrucao em row_to_entity_report nao assume
        # que os dois vem sempre juntos.
        original = EntityReport(
            entity_id="urn:ngsi-ld:Streetlight:003",
            entity_type=EntityType("Streetlight"),
            data_model=_DATA_MODEL,
            status=ConformanceStatus.CONFORMANT,
            violations=[],
            semantic_analysis_skipped=False,
            processing_duration_seconds=0.8,
            semantic_analysis_usage=SemanticAnalysisUsage(
                backend=InferenceBackend.BEDROCK, prompt_tokens=120, completion_tokens=45
            ),
        )

        payload = entity_report_to_rows(uuid4(), original)
        restored = row_to_entity_report(
            payload["report"], payload["violations"], payload["recommendations"]
        )

        assert restored == original

    def test_reprocessing_the_same_report_id_keeps_it_stable(self):
        # E' o mecanismo que sustenta a idempotencia de append_report
        # (secao 2 do spec): o Repository passa o mesmo report_id de volta
        # quando ja existe uma linha para (run_id, entity_id).
        run_id = uuid4()
        report = _full_report("urn:ngsi-ld:Streetlight:001")
        fixed_report_id = uuid4()

        payload = entity_report_to_rows(run_id, report, report_id=fixed_report_id)

        assert payload["report"]["id"] == fixed_report_id
        assert all(v["report_id"] == fixed_report_id for v in payload["violations"])
        assert all(r["report_id"] == fixed_report_id for r in payload["recommendations"])


class TestAuditRunRoundTrip:
    def test_run_with_a_report_round_trips_through_rows(self):
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/streetlights")
        report = _full_report("urn:1")
        run = AuditRun.create(
            tenant=tenant, entity_type=EntityType("Streetlight"), broker_url="http://localhost:1026"
        )
        run.add_report(report)
        run.status = RunStatus.COMPLETED
        run.finished_at = datetime(2026, 1, 3, tzinfo=timezone.utc)

        run_row = audit_run_to_row(run)
        report_payload = entity_report_to_rows(run.id, report)
        restored_report = row_to_entity_report(
            report_payload["report"], report_payload["violations"], report_payload["recommendations"]
        )
        restored_run = row_to_audit_run(run_row, reports=[restored_report])

        assert restored_run == run

    def test_run_without_reports_round_trips(self):
        tenant = Tenant(fiware_service="openiot")
        run = AuditRun.create(
            tenant=tenant, entity_type=None, broker_url="http://localhost:1026"
        )

        run_row = audit_run_to_row(run)
        restored = row_to_audit_run(run_row, reports=[])

        assert restored == run


class TestSummaryViewMapping:
    def test_summary_view_carries_aggregate_counters_not_full_reports(self):
        tenant = Tenant(fiware_service="openiot")
        run = AuditRun.create(
            tenant=tenant, entity_type=EntityType("Streetlight"), broker_url="http://localhost:1026"
        )
        run.add_report(_full_report("urn:1"))

        view = row_to_audit_run_summary_view(audit_run_to_row(run))

        assert view.id == run.id
        assert view.summary == run.summary
        assert not hasattr(view, "reports")
