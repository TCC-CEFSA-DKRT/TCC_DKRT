"""Fase 1 — EntityReport entity. Ver .cursor/specs/fase1.spec.md, secao 2.2."""

from datetime import datetime, timezone

import pytest

from auditor.domain.entities.entity_report import (
    EntityReport,
    InferenceBackend,
    SchemaOrigin,
    SchemaSource,
    SemanticAnalysisUsage,
)
from auditor.domain.entities.violation import (
    DetectionSource,
    Violation,
    ViolationSeverity,
)
from auditor.domain.errors import InconsistentEntityReportError
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType

_DATA_MODEL = DataModelRef(
    subject="dataModel.Streetlighting",
    model_name="Streetlight",
    version="1.0.0",
    schema_url="https://example.org/schema.json",
)


def _error_violation() -> Violation:
    return Violation(
        attribute_path="location",
        severity=ViolationSeverity.ERROR,
        rule="required_property_missing",
        expected="present",
        found="absent",
        message="test",
        detected_by=DetectionSource.STRUCTURAL,
    )


class TestEntityReportInvariants:
    def test_no_data_model_requires_no_model_found_status(self):
        with pytest.raises(InconsistentEntityReportError):
            EntityReport(
                entity_id="urn:ngsi-ld:Streetlight:001",
                entity_type=EntityType("Streetlight"),
                data_model=None,
                status=ConformanceStatus.CONFORMANT,
                violations=[],
            )

    def test_no_model_found_requires_no_data_model(self):
        with pytest.raises(InconsistentEntityReportError):
            EntityReport(
                entity_id="urn:ngsi-ld:Streetlight:001",
                entity_type=EntityType("Streetlight"),
                data_model=_DATA_MODEL,
                status=ConformanceStatus.NO_MODEL_FOUND,
                violations=[],
            )

    def test_conformant_status_with_error_violation_raises(self):
        with pytest.raises(InconsistentEntityReportError):
            EntityReport(
                entity_id="urn:ngsi-ld:Streetlight:001",
                entity_type=EntityType("Streetlight"),
                data_model=_DATA_MODEL,
                status=ConformanceStatus.CONFORMANT,
                violations=[_error_violation()],
            )

    def test_no_model_found_is_valid_regardless_of_violations(self):
        report = EntityReport(
            entity_id="urn:ngsi-ld:Streetlight:001",
            entity_type=EntityType("Streetlight"),
            data_model=None,
            status=ConformanceStatus.NO_MODEL_FOUND,
            violations=[],
        )
        assert report.status == ConformanceStatus.NO_MODEL_FOUND


class TestEntityReportSchemaUnavailable:
    """Ajuste retroativo da Fase 2 — ver .cursor/specs/fase2.spec.md, secao 4."""

    def test_schema_unavailable_is_valid_with_data_model_and_no_violations(self):
        report = EntityReport(
            entity_id="urn:ngsi-ld:Streetlight:001",
            entity_type=EntityType("Streetlight"),
            data_model=_DATA_MODEL,
            status=ConformanceStatus.SCHEMA_UNAVAILABLE,
            violations=[],
        )
        assert report.status == ConformanceStatus.SCHEMA_UNAVAILABLE
        assert report.status != ConformanceStatus.NO_MODEL_FOUND


class TestEntityReportSchemaOrigin:
    def test_cache_origin_is_preserved_and_visible(self):
        origin = SchemaOrigin(source=SchemaSource.CACHE, fetched_at=datetime.now(timezone.utc))
        report = EntityReport(
            entity_id="urn:ngsi-ld:Streetlight:001",
            entity_type=EntityType("Streetlight"),
            data_model=_DATA_MODEL,
            status=ConformanceStatus.CONFORMANT,
            violations=[],
            schema_origin=origin,
        )
        assert report.schema_origin is not None
        assert report.schema_origin.source == SchemaSource.CACHE
        assert "cache" in repr(report).lower()


class TestEntityReportMeasurement:
    """Fase 10 (.cursor/specs/fase10.spec.md, secao 3.3/3.4) —
    instrumentacao de tempo/custo por entidade. Ambos os campos sao
    opcionais e independentes das invariantes de status/violations acima."""

    def test_defaults_to_no_measurement(self):
        report = EntityReport(
            entity_id="urn:ngsi-ld:Streetlight:001",
            entity_type=EntityType("Streetlight"),
            data_model=_DATA_MODEL,
            status=ConformanceStatus.CONFORMANT,
            violations=[],
        )
        assert report.processing_duration_seconds is None
        assert report.semantic_analysis_usage is None

    def test_carries_duration_and_ollama_usage(self):
        usage = SemanticAnalysisUsage(backend=InferenceBackend.OLLAMA, compute_seconds=1.5)
        report = EntityReport(
            entity_id="urn:ngsi-ld:Streetlight:001",
            entity_type=EntityType("Streetlight"),
            data_model=_DATA_MODEL,
            status=ConformanceStatus.CONFORMANT,
            violations=[],
            processing_duration_seconds=3.2,
            semantic_analysis_usage=usage,
        )
        assert report.processing_duration_seconds == 3.2
        assert report.semantic_analysis_usage is not None
        assert report.semantic_analysis_usage.backend == InferenceBackend.OLLAMA
        assert report.semantic_analysis_usage.compute_seconds == 1.5
        assert report.semantic_analysis_usage.prompt_tokens is None

    def test_carries_bedrock_token_usage(self):
        usage = SemanticAnalysisUsage(
            backend=InferenceBackend.BEDROCK, prompt_tokens=100, completion_tokens=30
        )
        assert usage.compute_seconds is None
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 30
