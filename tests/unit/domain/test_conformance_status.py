"""Fase 1 — ConformanceStatus. Ver .cursor/specs/fase1.spec.md, secao 1.1."""

from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.value_objects.conformance_status import ConformanceStatus


def _violation(severity: ViolationSeverity) -> Violation:
    return Violation(
        attribute_path="illuminanceLevel",
        severity=severity,
        rule="test_rule",
        expected=None,
        found=None,
        message="test",
        detected_by=DetectionSource.STRUCTURAL,
    )


class TestConformanceStatusDerive:
    def test_no_violations_is_conformant(self):
        assert ConformanceStatus.derive([], model_found=True) == ConformanceStatus.CONFORMANT

    def test_only_warnings_is_partial(self):
        violations = [_violation(ViolationSeverity.WARNING)]
        assert ConformanceStatus.derive(violations, model_found=True) == ConformanceStatus.PARTIAL

    def test_any_error_is_non_conformant(self):
        violations = [_violation(ViolationSeverity.WARNING), _violation(ViolationSeverity.ERROR)]
        assert (
            ConformanceStatus.derive(violations, model_found=True)
            == ConformanceStatus.NON_CONFORMANT
        )

    def test_model_not_found_overrides_everything(self):
        violations = [_violation(ViolationSeverity.ERROR)]
        assert (
            ConformanceStatus.derive(violations, model_found=False)
            == ConformanceStatus.NO_MODEL_FOUND
        )
