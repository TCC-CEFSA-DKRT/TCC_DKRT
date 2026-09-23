"""Fase 1 — StructuralValidator. Ver .cursor/specs/fase1.spec.md, secao 3.

O schema usado aqui (tests/fixtures/schemas/streetlight_schema.json) e um
subconjunto representativo e apenas-para-teste do schema real do Streetlight
Smart Data Model — conforme a nota no topo de fase1.spec.md, a lista
definitiva de `required` deve vir do schema.json ao vivo (SchemaCatalogPort,
Fase 2), nao deste fixture.
"""

import json
from pathlib import Path

import pytest

from auditor.domain.entities.violation import ViolationSeverity
from auditor.domain.services.structural_validator import StructuralValidator

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def load_entity(name: str) -> dict:
    return json.loads((FIXTURES_DIR / "entities" / name).read_text(encoding="utf-8"))


def load_schema(name: str) -> dict:
    return json.loads((FIXTURES_DIR / "schemas" / name).read_text(encoding="utf-8"))


@pytest.fixture
def schema() -> dict:
    return load_schema("streetlight_schema.json")


@pytest.fixture
def validator() -> StructuralValidator:
    return StructuralValidator()


def violations_with_rule(violations, rule):
    return [v for v in violations if v.rule == rule]


class TestRequiredProperty:
    def test_missing_required_property_is_reported(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        del entity["lanternHeight"]

        violations = validator.validate(entity, schema)

        matches = violations_with_rule(violations, "required_property_missing")
        assert len(matches) == 1
        assert matches[0].attribute_path == "lanternHeight"
        assert matches[0].severity == ViolationSeverity.ERROR

    def test_all_required_present_produces_no_missing_violation(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        violations = validator.validate(entity, schema)
        assert violations_with_rule(violations, "required_property_missing") == []

    def test_conditional_requirement_satisfied_by_alternative(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        del entity["location"]
        entity["address"] = {"streetAddress": "Av. Paulista", "addressLocality": "Sao Paulo"}

        violations = validator.validate(entity, schema)

        assert violations_with_rule(violations, "required_property_missing") == []


class TestTypeMismatch:
    def test_string_instead_of_number_is_reported(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        entity["illuminanceLevel"] = "0.8"

        violations = validator.validate(entity, schema)

        matches = violations_with_rule(violations, "type_mismatch")
        assert len(matches) == 1
        assert matches[0].expected == "number"
        assert matches[0].found == "string"
        assert matches[0].severity == ViolationSeverity.ERROR

    def test_number_out_of_range_is_reported(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        entity["illuminanceLevel"] = 1.5

        violations = validator.validate(entity, schema)

        matches = violations_with_rule(violations, "value_out_of_range")
        assert len(matches) == 1
        assert matches[0].severity == ViolationSeverity.ERROR


class TestFormat:
    def test_invalid_date_time_is_reported(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        entity["dateModified"] = "ontem"

        violations = validator.validate(entity, schema)

        matches = violations_with_rule(violations, "format_invalid")
        assert len(matches) == 1
        assert matches[0].expected == "date-time"
        assert matches[0].severity == ViolationSeverity.ERROR

    def test_valid_iso8601_produces_no_format_violation(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        entity["dateModified"] = "2026-08-15T10:00:00Z"

        violations = validator.validate(entity, schema)

        assert violations_with_rule(violations, "format_invalid") == []


class TestEnum:
    def test_value_outside_enum_is_reported(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        entity["lanternMaterial"] = "iron"

        violations = validator.validate(entity, schema)

        matches = violations_with_rule(violations, "enum_violation")
        assert len(matches) == 1
        assert matches[0].severity == ViolationSeverity.ERROR
        for allowed in ("steel", "aluminium", "wood", "other"):
            assert allowed in matches[0].expected


class TestUnexpectedProperty:
    def test_property_outside_schema_is_warning_not_error(self, validator, schema):
        entity = load_entity("streetlight_partial.json")

        violations = validator.validate(entity, schema)

        matches = violations_with_rule(violations, "unexpected_property")
        assert len(matches) == 1
        assert matches[0].attribute_path == "temp"
        assert matches[0].severity == ViolationSeverity.WARNING

    def test_unexpected_property_carries_fields_fase7_contract_needs(self, validator, schema):
        # Documenta o contrato com a Fase 7: um WARNING de unexpected_property e
        # justamente o sinal que deve acionar semantic_analysis_skipped=False
        # quando o RunAuditUseCase (Fase 4) ligar as duas pontas. Este teste so
        # verifica o lado do Nivel 1: a violacao sai com os campos que a
        # Fase 4/7 vao precisar.
        entity = load_entity("streetlight_partial.json")
        violations = validator.validate(entity, schema)
        matches = violations_with_rule(violations, "unexpected_property")
        assert matches[0].detected_by.value == "structural"


class TestFullyConformantEntity:
    def test_no_violations_for_conformant_entity(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        assert validator.validate(entity, schema) == []


class TestNonConformantFixture:
    def test_non_conformant_fixture_has_exactly_two_error_violations(self, validator, schema):
        entity = load_entity("streetlight_non_conformant.json")
        violations = validator.validate(entity, schema)
        errors = [v for v in violations if v.severity == ViolationSeverity.ERROR]
        assert len(errors) == 2
        assert {v.rule for v in errors} == {"required_property_missing", "type_mismatch"}


class TestMultipleSimultaneousViolations:
    def test_reports_every_violation_not_just_the_first(self, validator, schema):
        entity = load_entity("streetlight_conformant.json")
        del entity["location"]
        entity["illuminanceLevel"] = "0.8"
        entity["temp"] = 21.5

        violations = validator.validate(entity, schema)

        rules_found = {v.rule for v in violations}
        assert "required_property_missing" in rules_found
        assert "type_mismatch" in rules_found
        assert "unexpected_property" in rules_found
        assert len(violations) == 3
