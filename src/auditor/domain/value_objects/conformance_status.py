"""ConformanceStatus value object — ver .cursor/specs/fase1.spec.md, secao 1.1.

Ajuste retroativo aplicado no inicio da Fase 2 (.cursor/specs/fase2.spec.md,
secao 4): adicionado SCHEMA_UNAVAILABLE, distinto de NO_MODEL_FOUND — o
catalogo confirma que existe um Smart Data Model para o entity_type, mas nao
foi possivel obter o conteudo do schema agora (nem ao vivo, nem em cache).
NO_MODEL_FOUND e definitivo; SCHEMA_UNAVAILABLE e transitorio (permite nova
tentativa depois).
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from auditor.domain.entities.violation import Violation


class ConformanceStatus(str, Enum):
    CONFORMANT = "conformant"
    PARTIAL = "partial"                        # violacoes apenas WARNING/INFO
    NON_CONFORMANT = "non_conformant"          # ao menos uma violacao ERROR
    NO_MODEL_FOUND = "no_model_found"          # catalogo confirma: nao existe
    SCHEMA_UNAVAILABLE = "schema_unavailable"  # existe, mas nao obtido agora

    @classmethod
    def derive(
        cls, violations: Iterable["Violation"], *, model_found: bool
    ) -> "ConformanceStatus":
        """Deriva o status a partir das violacoes — o status nunca e definido
        independentemente desta regra (ver invariante de `EntityReport`).

        Nao cobre SCHEMA_UNAVAILABLE: esse status nunca e derivado de
        violacoes (nao ha violacoes possiveis sem o conteudo do schema) — e
        atribuido diretamente por quem constroi o EntityReport quando o
        SchemaCatalogPort sinaliza indisponibilidade (Fase 2)."""
        if not model_found:
            return cls.NO_MODEL_FOUND

        from auditor.domain.entities.violation import ViolationSeverity

        violations = list(violations)
        if not violations:
            return cls.CONFORMANT
        if any(v.severity == ViolationSeverity.ERROR for v in violations):
            return cls.NON_CONFORMANT
        return cls.PARTIAL
