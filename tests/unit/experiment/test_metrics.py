"""Testes do calculo de metricas da Fase 10 — ver .cursor/specs/fase10.spec.md,
secao 6: fixtures sinteticas de resultado conhecido, sem depender do sistema
real, de Orion nem de SLM. Todos os numeros abaixo sao verificaveis a mao.
"""

from __future__ import annotations

import pytest

from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.experiment.metrics import (
    EntityTiming,
    ExpectedViolation,
    HallucinationReason,
    aggregate_precision_recall_f1,
    check_hallucination,
    exclusive_slm_detection_rate,
    hallucination_rate,
    inference_cost_bedrock,
    inference_cost_ollama,
    precision_recall_f1,
    time_distribution_by_level,
)

STRUCTURAL = DetectionSource.STRUCTURAL
SEMANTIC = DetectionSource.SEMANTIC
ERROR = ViolationSeverity.ERROR


def _violation(rule: str, attribute_path: str, *, detected_by: DetectionSource) -> Violation:
    return Violation(
        attribute_path=attribute_path,
        severity=ERROR,
        rule=rule,
        expected=None,
        found=None,
        message=f"{rule} em {attribute_path}",
        detected_by=detected_by,
    )


def _expected(rule: str, attribute_path: str, *, detected_by: DetectionSource) -> ExpectedViolation:
    return ExpectedViolation(
        rule=rule, attribute_path=attribute_path, severity=ERROR, detected_by=detected_by
    )


# ---------------------------------------------------------------------------
# 3.1 — precision / recall / F1
# ---------------------------------------------------------------------------


class TestPrecisionRecallF1:
    def test_matches_manual_calculation_for_a_single_entity_and_level(self):
        detected = [
            _violation("required_property_missing", "location", detected_by=STRUCTURAL),
            _violation("type_mismatch", "temperature", detected_by=STRUCTURAL),  # falso positivo
            _violation("synonym_mismatch", "temp", detected_by=SEMANTIC),  # nivel diferente
        ]
        expected = [
            _expected("required_property_missing", "location", detected_by=STRUCTURAL),
            _expected("format_invalid", "dateObserved", detected_by=STRUCTURAL),  # nao detectada
            _expected("synonym_mismatch", "temp", detected_by=SEMANTIC),
        ]

        structural_result = precision_recall_f1(detected, expected, level=STRUCTURAL)

        # TP=1 (location), FP=1 (temperature), FN=1 (dateObserved)
        assert structural_result.true_positives == 1
        assert structural_result.false_positives == 1
        assert structural_result.false_negatives == 1
        assert structural_result.precision == pytest.approx(0.5)
        assert structural_result.recall == pytest.approx(0.5)
        assert structural_result.f1 == pytest.approx(0.5)

    def test_never_mixes_levels_in_the_same_calculation(self):
        detected = [_violation("synonym_mismatch", "temp", detected_by=SEMANTIC)]
        expected = [_expected("synonym_mismatch", "temp", detected_by=SEMANTIC)]

        semantic_result = precision_recall_f1(detected, expected, level=SEMANTIC)

        assert semantic_result.precision == pytest.approx(1.0)
        assert semantic_result.recall == pytest.approx(1.0)
        assert semantic_result.f1 == pytest.approx(1.0)

    def test_reports_none_instead_of_dividing_by_zero_when_there_is_no_data(self):
        result = precision_recall_f1([], [], level=STRUCTURAL)

        assert result.precision is None
        assert result.recall is None
        assert result.f1 is None
        assert (result.true_positives, result.false_positives, result.false_negatives) == (0, 0, 0)

    def test_aggregate_sums_raw_counts_across_entities_before_dividing(self):
        entity_a_detected = [
            _violation("required_property_missing", "location", detected_by=STRUCTURAL),
            _violation("type_mismatch", "temperature", detected_by=STRUCTURAL),
        ]
        entity_a_expected = [
            _expected("required_property_missing", "location", detected_by=STRUCTURAL),
            _expected("format_invalid", "dateObserved", detected_by=STRUCTURAL),
        ]
        entity_b_detected = [
            _violation("required_property_missing", "address", detected_by=STRUCTURAL),
            _violation("enum_violation", "status", detected_by=STRUCTURAL),
        ]
        entity_b_expected = [
            _expected("required_property_missing", "address", detected_by=STRUCTURAL),
            _expected("enum_violation", "status", detected_by=STRUCTURAL),
        ]

        result = aggregate_precision_recall_f1(
            [
                (entity_a_detected, entity_a_expected),
                (entity_b_detected, entity_b_expected),
            ],
            level=STRUCTURAL,
        )

        # TP=3 (location, address, status), FP=1 (temperature), FN=1 (dateObserved)
        assert (result.true_positives, result.false_positives, result.false_negatives) == (3, 1, 1)
        assert result.precision == pytest.approx(0.75)
        assert result.recall == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# 3.2 — violacoes exclusivas do SLM
# ---------------------------------------------------------------------------


class TestExclusiveSlmDetectionRate:
    def test_matches_manual_calculation_across_entities(self):
        entity_a = (
            [_violation("synonym_mismatch", "temp", detected_by=SEMANTIC)],
            [
                _expected("synonym_mismatch", "temp", detected_by=SEMANTIC),
                _expected("unit_mismatch", "batteryLevel", detected_by=SEMANTIC),  # nao detectada
            ],
        )
        entity_b = (
            [_violation("synonym_mismatch", "addr", detected_by=SEMANTIC)],
            [_expected("synonym_mismatch", "addr", detected_by=SEMANTIC)],
        )

        rate = exclusive_slm_detection_rate([entity_a, entity_b])

        assert (rate.covered, rate.total) == (2, 3)
        assert rate.value == pytest.approx(2 / 3)

    def test_reports_none_when_dataset_has_no_semantic_exclusive_case(self):
        entity = (
            [_violation("required_property_missing", "location", detected_by=STRUCTURAL)],
            [_expected("required_property_missing", "location", detected_by=STRUCTURAL)],
        )

        rate = exclusive_slm_detection_rate([entity])

        assert rate.value is None
        assert (rate.covered, rate.total) == (0, 0)


# ---------------------------------------------------------------------------
# 3.3 — tempo por entidade
# ---------------------------------------------------------------------------


class TestTimeDistributionByLevel:
    def test_matches_manual_percentiles_for_both_series(self):
        timings = [
            EntityTiming("e1", 1.0, reached_level2=False),
            EntityTiming("e2", 2.0, reached_level2=False),
            EntityTiming("e3", 3.0, reached_level2=False),
            EntityTiming("e4", 4.0, reached_level2=False),
            EntityTiming("e5", 5.0, reached_level2=False),
            EntityTiming("e6", 10.0, reached_level2=True),
            EntityTiming("e7", 20.0, reached_level2=True),
        ]

        result = time_distribution_by_level(timings)

        level1_only = result["level1_only"]
        assert level1_only.count == 5
        assert level1_only.p50 == pytest.approx(3.0)
        assert level1_only.p95 == pytest.approx(5.0)
        assert level1_only.maximum == pytest.approx(5.0)

        level1_and_level2 = result["level1_and_level2"]
        assert level1_and_level2.count == 2
        assert level1_and_level2.p50 == pytest.approx(10.0)
        assert level1_and_level2.p95 == pytest.approx(20.0)
        assert level1_and_level2.maximum == pytest.approx(20.0)

    def test_reports_none_for_a_series_with_no_entities(self):
        result = time_distribution_by_level([EntityTiming("e1", 1.0, reached_level2=False)])

        empty_series = result["level1_and_level2"]
        assert (empty_series.p50, empty_series.p95, empty_series.maximum) == (None, None, None)
        assert empty_series.count == 0


# ---------------------------------------------------------------------------
# 3.4 — custo de inferencia
# ---------------------------------------------------------------------------


class TestInferenceCost:
    def test_ollama_reports_compute_seconds_never_usd(self):
        result = inference_cost_ollama([1.5, 2.5, 4.0])

        assert result.unit == "cpu_gpu_seconds"
        assert result.total == pytest.approx(8.0)
        assert result.per_entity_average == pytest.approx(8.0 / 3)

    def test_bedrock_reports_usd_from_token_counts(self):
        result = inference_cost_bedrock([1000, 500], price_per_1k_tokens=0.002)

        assert result.unit == "usd"
        assert result.total == pytest.approx(0.003)
        assert result.per_entity_average == pytest.approx(0.0015)

    def test_average_is_none_without_dividing_by_zero_when_empty(self):
        result = inference_cost_ollama([])

        assert result.total == 0.0
        assert result.per_entity_average is None


# ---------------------------------------------------------------------------
# 3.5 — taxa de alucinacao
# ---------------------------------------------------------------------------


_SCHEMA = {
    "required": ["temperature"],
    "additionalProperties": True,
    "properties": {"temperature": {"type": "number"}},
}
_ENTITY = {"id": "urn:ngsi-ld:Streetlight:1", "type": "Streetlight", "temp": 21.5}
_TARGETED_VIOLATION = _violation(
    "required_property_missing", "temperature", detected_by=STRUCTURAL
)


def _recommendation(
    *, attribute_path: str, action: RecommendationAction, proposed_patch: dict
) -> Recommendation:
    return Recommendation(
        attribute_path=attribute_path,
        action=action,
        proposed_patch=proposed_patch,
        rationale="teste",
        confidence=0.9,
    )


class TestCheckHallucination:
    def test_a_patch_that_actually_resolves_the_violation_is_not_hallucinated(self):
        recommendation = _recommendation(
            attribute_path="temperature",
            action=RecommendationAction.RENAME_ATTRIBUTE,
            proposed_patch={"from": "temp", "to": "temperature"},
        )

        result = check_hallucination(
            recommendation,
            targeted_violation=_TARGETED_VIOLATION,
            entity=_ENTITY,
            schema=_SCHEMA,
        )

        assert result.is_hallucinated is False
        assert result.reasons == ()

    def test_the_symmetric_patch_that_does_not_resolve_anything_is_hallucinated(self):
        # Mesma entidade/schema/violacao-alvo do teste anterior — so o patch
        # muda (renomeia para um nome errado em vez de "temperature").
        recommendation = _recommendation(
            attribute_path="temperature",
            action=RecommendationAction.RENAME_ATTRIBUTE,
            proposed_patch={"from": "temp", "to": "temp2"},
        )

        result = check_hallucination(
            recommendation,
            targeted_violation=_TARGETED_VIOLATION,
            entity=_ENTITY,
            schema=_SCHEMA,
        )

        assert result.is_hallucinated is True
        assert result.reasons == (HallucinationReason.PATCH_DOES_NOT_RESOLVE,)

    def test_condition_1_flags_an_attribute_the_schema_does_not_have(self):
        recommendation = _recommendation(
            attribute_path="temperture_typo",
            action=RecommendationAction.FIX_TYPE,
            proposed_patch={"value": 21.5},
        )

        result = check_hallucination(
            recommendation,
            targeted_violation=_TARGETED_VIOLATION,
            entity=_ENTITY,
            schema=_SCHEMA,
        )

        assert HallucinationReason.UNKNOWN_ATTRIBUTE in result.reasons

    def test_condition_3_flags_an_action_incompatible_with_the_violation_rule(self):
        # fix_type para uma violacao que era, na verdade,
        # required_property_missing — exatamente o exemplo do spec (secao 3.5).
        recommendation = _recommendation(
            attribute_path="temperature",
            action=RecommendationAction.FIX_TYPE,
            proposed_patch={"value": 21.5},
        )

        result = check_hallucination(
            recommendation,
            targeted_violation=_TARGETED_VIOLATION,
            entity=_ENTITY,
            schema=_SCHEMA,
        )

        # O patch de fix_type acaba preenchendo 'temperature' e resolvendo a
        # violacao por acidente — isola condicao 3 sem contaminar com a 2.
        assert result.reasons == (HallucinationReason.ACTION_MISMATCH,)


class TestHallucinationRate:
    def test_reports_none_instead_of_zero_percent_when_there_are_no_recommendations(self):
        rate = hallucination_rate([])

        assert rate.value is None
        assert (rate.hallucinated, rate.total) == (0, 0)
        assert all(count == 0 for count in rate.by_reason.values())

    def test_matches_manual_calculation_and_counts_each_reason_individually(self):
        not_hallucinated = check_hallucination(
            _recommendation(
                attribute_path="temperature",
                action=RecommendationAction.RENAME_ATTRIBUTE,
                proposed_patch={"from": "temp", "to": "temperature"},
            ),
            targeted_violation=_TARGETED_VIOLATION,
            entity=_ENTITY,
            schema=_SCHEMA,
        )
        hallucinated = check_hallucination(
            _recommendation(
                attribute_path="temperture_typo",
                action=RecommendationAction.FIX_TYPE,
                proposed_patch={"value": 21.5},
            ),
            targeted_violation=_TARGETED_VIOLATION,
            entity=_ENTITY,
            schema=_SCHEMA,
        )

        rate = hallucination_rate([not_hallucinated, hallucinated])

        assert rate.value == pytest.approx(0.5)
        assert (rate.hallucinated, rate.total) == (1, 2)
        assert rate.by_reason[HallucinationReason.UNKNOWN_ATTRIBUTE] == 1
