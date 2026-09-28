"""Fase 1 — AuditRun aggregate. Ver .cursor/specs/fase1.spec.md, secao 2.4."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from auditor.domain.entities.audit_run import AuditRun, RunStatus, RunSummary
from auditor.domain.entities.entity_report import EntityReport
from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.errors import InvariantViolationError
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant

_TENANT = Tenant(fiware_service="openiot")
_DATA_MODEL = DataModelRef(
    subject="dataModel.Streetlighting",
    model_name="Streetlight",
    version="1.0.0",
    schema_url="https://example.org/schema.json",
)


def _report(status: ConformanceStatus, entity_id: str) -> EntityReport:
    violations = (
        [
            Violation(
                attribute_path="location",
                severity=ViolationSeverity.ERROR,
                rule="required_property_missing",
                expected="present",
                found="absent",
                message="test",
                detected_by=DetectionSource.STRUCTURAL,
            )
        ]
        if status == ConformanceStatus.NON_CONFORMANT
        else []
    )
    return EntityReport(
        entity_id=entity_id,
        entity_type=EntityType("Streetlight"),
        data_model=None if status == ConformanceStatus.NO_MODEL_FOUND else _DATA_MODEL,
        status=status,
        violations=violations,
    )


class TestRunSummary:
    def test_counters_must_sum_to_total(self):
        with pytest.raises(InvariantViolationError):
            RunSummary(
                total_entities=3,
                conformant_count=1,
                non_conformant_count=1,
                partial_count=0,
                no_model_count=0,
                schema_unavailable_count=0,
            )

    def test_empty_summary_is_all_zero(self):
        summary = RunSummary.empty()
        assert summary.total_entities == 0

    def test_schema_unavailable_reports_are_counted_too(self):
        # Ajuste retroativo da Fase 3 — ver docstring de RunSummary.
        reports = [
            _report(ConformanceStatus.CONFORMANT, "urn:1"),
            _report(ConformanceStatus.SCHEMA_UNAVAILABLE, "urn:2"),
        ]
        summary = RunSummary.from_reports(reports)
        assert summary.total_entities == 2
        assert summary.schema_unavailable_count == 1


class TestAuditRun:
    def test_completed_run_requires_finished_at(self):
        with pytest.raises(InvariantViolationError):
            AuditRun(
                id=uuid4(),
                tenant=_TENANT,
                entity_type=EntityType("Streetlight"),
                status=RunStatus.COMPLETED,
                reports=[],
                summary=RunSummary.empty(),
                started_at=datetime.now(timezone.utc),
                finished_at=None,
                broker_url="http://localhost:1026",
            )

    def test_no_entities_found_run_requires_finished_at(self):
        with pytest.raises(InvariantViolationError):
            AuditRun(
                id=uuid4(),
                tenant=_TENANT,
                entity_type=EntityType("Streetlight"),
                status=RunStatus.NO_ENTITIES_FOUND,
                reports=[],
                summary=RunSummary.empty(),
                started_at=datetime.now(timezone.utc),
                finished_at=None,
                broker_url="http://localhost:1026",
            )

    def test_freshly_created_run_is_queued_and_empty(self):
        run = AuditRun.create(
            tenant=_TENANT,
            entity_type=EntityType("Streetlight"),
            broker_url="http://localhost:1026",
        )
        assert run.status == RunStatus.QUEUED
        assert run.reports == []
        assert run.finished_at is None

    def test_add_report_recomputes_summary_automatically(self):
        run = AuditRun.create(
            tenant=_TENANT,
            entity_type=EntityType("Streetlight"),
            broker_url="http://localhost:1026",
        )
        run.add_report(_report(ConformanceStatus.CONFORMANT, "urn:1"))
        run.add_report(_report(ConformanceStatus.NON_CONFORMANT, "urn:2"))
        run.add_report(_report(ConformanceStatus.NO_MODEL_FOUND, "urn:3"))
        run.add_report(_report(ConformanceStatus.SCHEMA_UNAVAILABLE, "urn:4"))

        assert run.summary.total_entities == 4
        assert run.summary.conformant_count == 1
        assert run.summary.non_conformant_count == 1
        assert run.summary.no_model_count == 1
        assert run.summary.schema_unavailable_count == 1
