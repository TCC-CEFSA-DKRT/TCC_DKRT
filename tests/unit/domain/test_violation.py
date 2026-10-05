"""Fase 1 — Violation entity. Ver .cursor/specs/fase1.spec.md, secao 2.1."""

import dataclasses

import pytest

from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity


class TestViolation:
    def test_is_immutable(self):
        violation = Violation(
            attribute_path="location",
            severity=ViolationSeverity.ERROR,
            rule="required_property_missing",
            expected="present",
            found="absent",
            message="Propriedade obrigatoria 'location' esta ausente.",
            detected_by=DetectionSource.STRUCTURAL,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            violation.severity = ViolationSeverity.WARNING

    @pytest.mark.parametrize("path", ["location", "address.streetName"])
    def test_accepts_simple_and_nested_attribute_paths(self, path):
        violation = Violation(
            attribute_path=path,
            severity=ViolationSeverity.WARNING,
            rule="unexpected_property",
            expected=None,
            found=path,
            message="test",
            detected_by=DetectionSource.STRUCTURAL,
        )
        assert violation.attribute_path == path
