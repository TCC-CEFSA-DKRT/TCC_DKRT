"""Violation entity — ver .cursor/specs/fase1.spec.md, secao 2.1."""

from dataclasses import dataclass
from enum import Enum


class ViolationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DetectionSource(str, Enum):
    STRUCTURAL = "structural"  # Nivel 1
    SEMANTIC = "semantic"      # Nivel 2 — Fase 7, fora do escopo desta fase


@dataclass(frozen=True)
class Violation:
    """Uma violacao de conformidade encontrada em um atributo de uma entidade.

    Imutavel: um achado de auditoria nao muda depois de gerado.
    """

    attribute_path: str
    severity: ViolationSeverity
    rule: str
    expected: str | None
    found: str | None
    message: str
    detected_by: DetectionSource
