"""Contrato de saida do SLM — validado, nunca texto livre. Ver
.cursor/specs/fase7.spec.md, secao 2.

A resposta crua do modelo (JSON) passa por validacao Pydantic aqui antes de
qualquer coisa virar `Violation`/`Recommendation` de dominio. Reaproveitado
por qualquer adaptador de `SemanticAnalyzerPort` (OllamaAnalyzer,
BedrockAnalyzer) — a validacao nao e' duplicada por adaptador (secao 5.1).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ValidationError

from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.errors import InvalidRecommendationError
from auditor.domain.ports.semantic_analyzer_port import SemanticAnalysisResult

_SEVERITY_BY_VALUE = {
    "error": ViolationSeverity.ERROR,
    "warning": ViolationSeverity.WARNING,
    "info": ViolationSeverity.INFO,
}


class _SemanticFindingSchema(BaseModel):
    attribute_path: str
    severity: Literal["error", "warning", "info"]
    rule: str
    message: str


class _SemanticRecommendationSchema(BaseModel):
    attribute_path: str
    action: Literal["rename_attribute", "add_missing_attribute", "fix_type", "fix_format"]
    proposed_patch: dict
    rationale: str
    confidence: float


class _SemanticAnalysisOutputSchema(BaseModel):
    findings: list[_SemanticFindingSchema] = []
    recommendations: list[_SemanticRecommendationSchema] = []


def parse_semantic_analysis_output(raw_text: str) -> SemanticAnalysisResult:
    """Ponto unico de conversao "texto cru do modelo" -> `SemanticAnalysisResult`
    de dominio. Qualquer falha (JSON invalido, campo obrigatorio faltando,
    invariante de dominio violado por um valor fora do intervalo esperado)
    vira `analysis_unavailable=True` — nunca uma excecao propagada para
    quem chamou (secao 2.1 do spec: os quatro casos de falha recebem
    exatamente o mesmo tratamento)."""
    try:
        raw = json.loads(raw_text)
        parsed = _SemanticAnalysisOutputSchema.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return SemanticAnalysisResult(analysis_unavailable=True)

    try:
        violations = tuple(
            Violation(
                attribute_path=finding.attribute_path,
                severity=_SEVERITY_BY_VALUE[finding.severity],
                rule=finding.rule,
                expected=None,
                found=None,
                message=finding.message,
                detected_by=DetectionSource.SEMANTIC,
            )
            for finding in parsed.findings
        )
        recommendations = tuple(
            Recommendation(
                attribute_path=rec.attribute_path,
                action=RecommendationAction(rec.action),
                proposed_patch=rec.proposed_patch,
                rationale=rec.rationale,
                confidence=rec.confidence,
            )
            for rec in parsed.recommendations
        )
    except InvalidRecommendationError:
        # Nunca deixa uma excecao de invariante de dominio (Fase 1) vazar
        # de uma saida de modelo nao confiavel (secao 2.1, ultimo caso).
        return SemanticAnalysisResult(analysis_unavailable=True)

    return SemanticAnalysisResult(
        violations=violations, recommendations=recommendations, analysis_unavailable=False
    )
