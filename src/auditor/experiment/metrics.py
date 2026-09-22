"""Calculo das cinco metricas da Fase 10 — ver .cursor/specs/fase10.spec.md,
secao 3 (definicao de cada metrica) e secao 6 (por que este modulo precisa de
teste isolado: "um script de metricas com bug invalidaria o experimento
inteiro mesmo com o sistema correto").

Puro, sem I/O — como um `domain/services/` (ex.: `StructuralValidator`), mas
vive fora de `domain/` porque nao faz parte do sistema de auditoria em si: e
ferramental de medicao usado so pelo experimento (`scripts/run_experiment.py`,
ainda nao escrito), nunca pela API/worker que atende trafego real. Todo tipo
usado aqui (`Violation`, `Recommendation`, `StructuralValidator`) e importado
de `auditor.domain`, nunca reimplementado.

Convencao de nomenclatura das funcoes: cada metrica tem uma funcao "por
entidade" (opera sobre os achados de UMA entidade) e, quando faz sentido
agregar, uma funcao correspondente que soma contagens brutas atraves de todo
o dataset ANTES de calcular a taxa final — nunca a media das taxas por
entidade, que e estatisticamente enviesada quando as entidades tem numeros
de violacoes diferentes entre si.

Nota sobre `Recommendation.proposed_patch`: o dominio (Fase 1/7) deixa esse
campo deliberadamente livre — `dict` sem sub-schema
(`auditor.infrastructure.llm.semantic_output_schema.py`,
`_SemanticRecommendationSchema.proposed_patch: dict`) e o prompt real
(`infrastructure/llm/prompts/semantic_diagnosis.md`) so pede `{...}` ao SLM.
Nao existe hoje, em nenhum lugar do codigo, uma convencao de "como aplicar um
patch" — a funcao `apply_patch` abaixo e uma convencao NOVA, introduzida
somente para permitir a verificacao automatica da condicao 2 da taxa de
alucinacao (secao 3.5). Quem chamar `check_hallucination` pode injetar
`apply_patch_fn` proprio caso o dataset real (ou o prompt) adote uma forma de
patch diferente da assumida aqui.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Any

from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.services.structural_validator import StructuralValidator

# ---------------------------------------------------------------------------
# 3.1 — Acuracia por nivel (precision / recall / F1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpectedViolation:
    """Forma que o metodo de calculo espera de uma entrada de
    `ground_truth.json` (fase10.spec.md, secao 1) — o parsing do arquivo em
    si (formato de dataset, secao 1) fica fora do escopo deste modulo."""

    rule: str
    attribute_path: str
    severity: ViolationSeverity
    detected_by: DetectionSource
    proposed_patch: dict | None = None


@dataclass(frozen=True)
class PrecisionRecallF1:
    """`precision`/`recall`/`f1` sao `None` quando o denominador correspondente
    e zero (nenhuma deteccao e nenhuma violacao esperada naquele nivel) — nunca
    uma divisao por zero silenciosa nem um `0.0` indistinguivel de "o sistema
    errou tudo" (mesmo cuidado da secao 6, terceiro caso de teste, aplicado
    aqui por consistencia)."""

    precision: float | None
    recall: float | None
    f1: float | None
    true_positives: int
    false_positives: int
    false_negatives: int


def _violation_key(rule: str, attribute_path: str) -> tuple[str, str]:
    return (rule, attribute_path)


def _level_counts(
    detected: Iterable[Violation],
    expected: Iterable[ExpectedViolation],
    *,
    level: DetectionSource,
) -> tuple[int, int, int]:
    detected_keys = {
        _violation_key(v.rule, v.attribute_path) for v in detected if v.detected_by == level
    }
    expected_keys = {
        _violation_key(e.rule, e.attribute_path) for e in expected if e.detected_by == level
    }
    true_positives = len(detected_keys & expected_keys)
    false_positives = len(detected_keys - expected_keys)
    false_negatives = len(expected_keys - detected_keys)
    return true_positives, false_positives, false_negatives


def _precision_recall_f1_from_counts(
    true_positives: int, false_positives: int, false_negatives: int
) -> PrecisionRecallF1:
    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else None
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else None
    )
    f1: float | None
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return PrecisionRecallF1(precision, recall, f1, true_positives, false_positives, false_negatives)


def precision_recall_f1(
    detected: Iterable[Violation],
    expected: Iterable[ExpectedViolation],
    *,
    level: DetectionSource,
) -> PrecisionRecallF1:
    """Precision/recall/F1 de uma unica entidade, para um nivel de deteccao —
    fase10.spec.md secao 3.1. Nunca mistura `STRUCTURAL` e `SEMANTIC`: chame
    uma vez por nivel."""
    counts = _level_counts(detected, expected, level=level)
    return _precision_recall_f1_from_counts(*counts)


def aggregate_precision_recall_f1(
    per_entity: Iterable[tuple[Iterable[Violation], Iterable[ExpectedViolation]]],
    *,
    level: DetectionSource,
) -> PrecisionRecallF1:
    """Mesma metrica, agregada sobre todo o dataset — soma TP/FP/FN de cada
    entidade primeiro, so entao calcula a taxa final (ver nota do modulo:
    nunca a media das taxas por entidade)."""
    total_tp = total_fp = total_fn = 0
    for detected, expected in per_entity:
        tp, fp, fn = _level_counts(detected, expected, level=level)
        total_tp += tp
        total_fp += fp
        total_fn += fn
    return _precision_recall_f1_from_counts(total_tp, total_fp, total_fn)


# ---------------------------------------------------------------------------
# 3.2 — Violacoes exclusivas do SLM
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rate:
    """`value` e `None` quando `total == 0` ("sem dados"), nunca `0.0`."""

    value: float | None
    covered: int
    total: int


def exclusive_slm_detection_rate(
    per_entity: Iterable[tuple[Iterable[Violation], Iterable[ExpectedViolation]]],
) -> Rate:
    """fase10.spec.md secao 3.2. `exclusivas_do_slm` e, por definicao da
    categoria do dataset (secao 1), toda violacao esperada com
    `detected_by=SEMANTIC` — sao as violacoes que a propria curadoria do
    dataset garante nao serem pegas pelo Nivel 1 sozinho (secao 1.1, segundo
    caso de teste do dataset)."""
    covered = 0
    total = 0
    for detected, expected in per_entity:
        detected_semantic_keys = {
            _violation_key(v.rule, v.attribute_path)
            for v in detected
            if v.detected_by == DetectionSource.SEMANTIC
        }
        for e in expected:
            if e.detected_by != DetectionSource.SEMANTIC:
                continue
            total += 1
            if _violation_key(e.rule, e.attribute_path) in detected_semantic_keys:
                covered += 1
    value = covered / total if total > 0 else None
    return Rate(value, covered, total)


# ---------------------------------------------------------------------------
# 3.3 — Tempo por entidade
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityTiming:
    entity_id: str
    duration_seconds: float
    reached_level2: bool


@dataclass(frozen=True)
class TimeDistribution:
    p50: float | None
    p95: float | None
    maximum: float | None
    count: int


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Metodo nearest-rank sobre uma lista ja ordenada — simples e
    verificavel a mao (secao 6: "casos de teste com numeros simples")."""
    if not sorted_values:
        raise ValueError("_percentile requer ao menos um valor.")
    rank = max(1, ceil(fraction * len(sorted_values)))
    index = min(rank, len(sorted_values)) - 1
    return sorted_values[index]


def _distribution(values: list[float]) -> TimeDistribution:
    if not values:
        return TimeDistribution(None, None, None, 0)
    ordered = sorted(values)
    return TimeDistribution(
        p50=_percentile(ordered, 0.50),
        p95=_percentile(ordered, 0.95),
        maximum=ordered[-1],
        count=len(ordered),
    )


def time_distribution_by_level(timings: Iterable[EntityTiming]) -> dict[str, TimeDistribution]:
    """fase10.spec.md secao 3.3 — duas series separadas: entidades que so
    passaram pelo Nivel 1 vs. entidades que tambem passaram pelo Nivel 2."""
    level1_only: list[float] = []
    level1_and_level2: list[float] = []
    for timing in timings:
        (level1_and_level2 if timing.reached_level2 else level1_only).append(
            timing.duration_seconds
        )
    return {
        "level1_only": _distribution(level1_only),
        "level1_and_level2": _distribution(level1_and_level2),
    }


# ---------------------------------------------------------------------------
# 3.4 — Custo de inferencia
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InferenceCost:
    """`unit` distingue explicitamente as duas grandezas — fase10.spec.md
    secao 3.4 e explicito: nunca comparar Ollama (tempo de CPU/GPU) e Bedrock
    (USD) como se fossem a mesma unidade."""

    unit: str  # "usd" ou "cpu_gpu_seconds"
    total: float
    per_entity_average: float | None


def inference_cost_bedrock(
    token_counts: Iterable[int], *, price_per_1k_tokens: float
) -> InferenceCost:
    counts = list(token_counts)
    total_cost = (sum(counts) / 1000) * price_per_1k_tokens
    average = total_cost / len(counts) if counts else None
    return InferenceCost(unit="usd", total=total_cost, per_entity_average=average)


def inference_cost_ollama(compute_seconds: Iterable[float]) -> InferenceCost:
    values = list(compute_seconds)
    total = sum(values)
    average = total / len(values) if values else None
    return InferenceCost(unit="cpu_gpu_seconds", total=total, per_entity_average=average)


# ---------------------------------------------------------------------------
# 3.5 — Taxa de alucinacao nas recomendacoes
# ---------------------------------------------------------------------------


class HallucinationReason(str, Enum):
    UNKNOWN_ATTRIBUTE = "unknown_attribute"  # condicao 1
    PATCH_DOES_NOT_RESOLVE = "patch_does_not_resolve"  # condicao 2
    ACTION_MISMATCH = "action_mismatch"  # condicao 3


@dataclass(frozen=True)
class HallucinationCheck:
    is_hallucinated: bool
    reasons: tuple[HallucinationReason, ...] = field(default_factory=tuple)


# Condicao 3: quais RecommendationAction sao semanticamente compativeis com
# qual `rule` do StructuralValidator (Fase 1) — as unicas rules de um
# conjunto fechado e conhecido hoje no codigo
# (`domain/services/structural_validator.py`). Uma violacao cujo `rule` nao
# esta neste mapa (tipicamente um `rule` inventado pelo proprio SLM para um
# achado puramente semantico, Fase 7) nao e avaliada pela condicao 3 —
# deliberado: nunca acusar alucinacao por uma regra de compatibilidade que
# nao temos como verificar formalmente.
_COMPATIBLE_ACTIONS_BY_RULE: dict[str, frozenset[RecommendationAction]] = {
    "required_property_missing": frozenset(
        {RecommendationAction.ADD_MISSING_ATTRIBUTE, RecommendationAction.RENAME_ATTRIBUTE}
    ),
    "type_mismatch": frozenset({RecommendationAction.FIX_TYPE}),
    "format_invalid": frozenset({RecommendationAction.FIX_FORMAT}),
    "value_out_of_range": frozenset({RecommendationAction.FIX_TYPE}),
    "enum_violation": frozenset({RecommendationAction.FIX_FORMAT, RecommendationAction.FIX_TYPE}),
    "unexpected_property": frozenset({RecommendationAction.RENAME_ATTRIBUTE}),
}


def apply_patch(entity: dict[str, Any], recommendation: Recommendation) -> dict[str, Any]:
    """Convencao de referencia para aplicar um `proposed_patch` — ver nota do
    modulo sobre por que essa convencao precisou ser inventada aqui. Um patch
    malformado (chaves ausentes/inesperadas) simplesmente nao altera a
    entidade, o que faz a revalidacao (condicao 2) corretamente continuar
    vendo a violacao original — nao precisa de tratamento especial."""
    patched = dict(entity)
    patch = recommendation.proposed_patch
    if recommendation.action == RecommendationAction.RENAME_ATTRIBUTE:
        old_name = patch.get("from")
        new_name = patch.get("to")
        if old_name is not None and new_name is not None and old_name in patched:
            patched[new_name] = patched.pop(old_name)
    elif recommendation.action == RecommendationAction.ADD_MISSING_ATTRIBUTE:
        if "value" in patch:
            patched[recommendation.attribute_path] = patch["value"]
    elif recommendation.action in (RecommendationAction.FIX_TYPE, RecommendationAction.FIX_FORMAT):
        if "value" in patch:
            patched[recommendation.attribute_path] = patch["value"]
    return patched


def check_hallucination(
    recommendation: Recommendation,
    *,
    targeted_violation: Violation,
    entity: dict[str, Any],
    schema: dict[str, Any],
    validator: StructuralValidator | None = None,
    apply_patch_fn: Callable[[dict[str, Any], Recommendation], dict[str, Any]] = apply_patch,
) -> HallucinationCheck:
    """fase10.spec.md secao 3.5 — as tres condicoes, cada uma individualmente
    contavel via `HallucinationCheck.reasons`. `targeted_violation` e a
    violacao (do `ground_truth.json` ou do `EntityReport`) que esta
    `Recommendation` alega corrigir — quem chama resolve esse pareamento
    (por `attribute_path`), este modulo nao adivinha."""
    validator = validator or StructuralValidator()
    reasons: list[HallucinationReason] = []

    # condicao 1
    known_attributes = set(schema.get("properties", {})) | {"id", "type"}
    if recommendation.attribute_path not in known_attributes:
        reasons.append(HallucinationReason.UNKNOWN_ATTRIBUTE)

    # condicao 2
    patched_entity = apply_patch_fn(entity, recommendation)
    remaining = validator.validate(patched_entity, schema)
    still_present = any(
        v.rule == targeted_violation.rule and v.attribute_path == targeted_violation.attribute_path
        for v in remaining
    )
    if still_present:
        reasons.append(HallucinationReason.PATCH_DOES_NOT_RESOLVE)

    # condicao 3
    compatible_actions = _COMPATIBLE_ACTIONS_BY_RULE.get(targeted_violation.rule)
    if compatible_actions is not None and recommendation.action not in compatible_actions:
        reasons.append(HallucinationReason.ACTION_MISMATCH)

    return HallucinationCheck(is_hallucinated=bool(reasons), reasons=tuple(reasons))


@dataclass(frozen=True)
class HallucinationRate:
    """`value` e `None` quando `total == 0` — "sem dados", nunca um `0%`
    indistinguivel de "zero alucinacoes observadas em muitas recomendacoes"
    (fase10.spec.md secao 6, terceiro caso de teste, literal)."""

    value: float | None
    hallucinated: int
    total: int
    by_reason: dict[HallucinationReason, int]


def hallucination_rate(checks: Iterable[HallucinationCheck]) -> HallucinationRate:
    checks = list(checks)
    by_reason: dict[HallucinationReason, int] = {reason: 0 for reason in HallucinationReason}
    hallucinated = 0
    for check in checks:
        if check.is_hallucinated:
            hallucinated += 1
        for reason in check.reasons:
            by_reason[reason] += 1
    total = len(checks)
    value = hallucinated / total if total > 0 else None
    return HallucinationRate(value, hallucinated, total, by_reason)
