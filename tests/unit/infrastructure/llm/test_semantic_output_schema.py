"""Fase 7 — parse_semantic_analysis_output. Ver .cursor/specs/fase7.spec.md,
secao 2.1. Puro, sem rede nem banco."""

from __future__ import annotations

import json

from auditor.domain.entities.violation import DetectionSource, ViolationSeverity
from auditor.infrastructure.llm.semantic_output_schema import parse_semantic_analysis_output


class TestValidOutput:
    def test_valid_json_populates_violations_and_recommendations(self):
        raw = json.dumps(
            {
                "findings": [
                    {
                        "attribute_path": "temp",
                        "severity": "error",
                        "rule": "attribute_name_synonym",
                        "message": "'temp' parece ser 'temperature' com nome errado.",
                    }
                ],
                "recommendations": [
                    {
                        "attribute_path": "temp",
                        "action": "rename_attribute",
                        "proposed_patch": {"from": "temp", "to": "temperature"},
                        "rationale": "sinonimo conhecido do glossario curado.",
                        "confidence": 0.9,
                    }
                ],
            }
        )

        result = parse_semantic_analysis_output(raw)

        assert result.analysis_unavailable is False
        assert len(result.violations) == 1
        assert result.violations[0].detected_by == DetectionSource.SEMANTIC
        assert result.violations[0].severity == ViolationSeverity.ERROR
        assert len(result.recommendations) == 1
        assert result.recommendations[0].action.value == "rename_attribute"


class TestMalformedOutput:
    def test_non_json_text_yields_analysis_unavailable(self):
        result = parse_semantic_analysis_output("desculpe, nao consigo ajudar com isso.")

        assert result.analysis_unavailable is True
        assert result.violations == ()
        assert result.recommendations == ()

    def test_json_missing_required_field_yields_analysis_unavailable(self):
        raw = json.dumps(
            {
                "findings": [],
                "recommendations": [
                    {
                        "attribute_path": "temp",
                        "action": "rename_attribute",
                        "proposed_patch": {"from": "temp", "to": "temperature"},
                        "rationale": "falta confidence",
                        # "confidence" ausente de proposito
                    }
                ],
            }
        )

        result = parse_semantic_analysis_output(raw)

        assert result.analysis_unavailable is True
        assert result.recommendations == ()

    def test_confidence_out_of_domain_range_yields_analysis_unavailable(self):
        raw = json.dumps(
            {
                "findings": [],
                "recommendations": [
                    {
                        "attribute_path": "temp",
                        "action": "rename_attribute",
                        "proposed_patch": {"from": "temp", "to": "temperature"},
                        "rationale": "confidence invalida",
                        "confidence": 1.5,
                    }
                ],
            }
        )

        result = parse_semantic_analysis_output(raw)

        assert result.analysis_unavailable is True
        assert result.recommendations == ()


class TestEmptyButValidOutput:
    def test_empty_findings_and_recommendations_is_a_valid_result(self):
        raw = json.dumps({"findings": [], "recommendations": []})

        result = parse_semantic_analysis_output(raw)

        assert result == parse_semantic_analysis_output(raw)
        assert result.analysis_unavailable is False
        assert result.violations == ()
        assert result.recommendations == ()
