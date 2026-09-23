"""Fase 1 — Recommendation entity. Ver .cursor/specs/fase1.spec.md, secao 2.3."""

import pytest

from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.errors import InvalidRecommendationError


def _make(**overrides):
    kwargs = dict(
        attribute_path="temp",
        action=RecommendationAction.RENAME_ATTRIBUTE,
        proposed_patch={"from": "temp", "to": "temperature"},
        rationale="Sinonimo comum para o nome de atributo padrao.",
        confidence=0.9,
    )
    kwargs.update(overrides)
    return Recommendation(**kwargs)


class TestRecommendation:
    def test_valid_construction(self):
        rec = _make()
        assert rec.action == RecommendationAction.RENAME_ATTRIBUTE

    @pytest.mark.parametrize("confidence", [1.5, -0.1])
    def test_confidence_out_of_range_raises(self, confidence):
        with pytest.raises(InvalidRecommendationError):
            _make(confidence=confidence)

    def test_empty_patch_raises(self):
        with pytest.raises(InvalidRecommendationError):
            _make(proposed_patch={})
