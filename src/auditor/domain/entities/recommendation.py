"""Recommendation entity — ver .cursor/specs/fase1.spec.md, secao 2.3."""

from dataclasses import dataclass
from enum import Enum

from auditor.domain.errors import InvalidRecommendationError


class RecommendationAction(str, Enum):
    RENAME_ATTRIBUTE = "rename_attribute"
    ADD_MISSING_ATTRIBUTE = "add_missing_attribute"
    FIX_TYPE = "fix_type"
    FIX_FORMAT = "fix_format"


@dataclass(frozen=True)
class Recommendation:
    """Uma correcao sugerida, estruturada e acionavel por maquina.

    `proposed_patch` e um dict simples (ex.: {"from": "temp", "to":
    "temperature"}) para que um futuro Nivel 3 possa consumi-la sem
    reinterpretar texto livre.
    """

    attribute_path: str
    action: RecommendationAction
    proposed_patch: dict
    rationale: str
    confidence: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise InvalidRecommendationError(
                f"Recommendation.confidence deve estar em [0.0, 1.0], "
                f"recebido {self.confidence}."
            )
        if not self.proposed_patch:
            raise InvalidRecommendationError(
                "Recommendation.proposed_patch nao pode ser vazio — uma "
                "recomendacao sem patch estruturado nao serve ao proposito de "
                "ser consumida no futuro pelo Nivel 3."
            )
