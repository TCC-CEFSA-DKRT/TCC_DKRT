"""SemanticAnalyzerPort — ver .cursor/specs/fase7.spec.md, secao 1.

E' esta porta que da' ao sistema o Nivel 2 de diagnostico (semantico, via
SLM/RAG) sobre o Nivel 1 (estrutural, deterministico, Fase 1-4). O
analisador so' analisa; nao busca nada por conta propria — `plain_values`/
`schema` (Fase 4/2) e `knowledge_chunks` (Fase 6, ja' recuperados por quem
monta o contexto) chegam prontos, porque esta porta nao sabe nada sobre
NgsiV2Mapper, SchemaCatalogPort nem KnowledgeRetrieverPort.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from auditor.domain.entities.entity_report import SemanticAnalysisUsage
from auditor.domain.entities.recommendation import Recommendation
from auditor.domain.entities.violation import Violation
from auditor.domain.errors import InconsistentSemanticAnalysisResultError
from auditor.domain.value_objects.entity_type import EntityType

if TYPE_CHECKING:
    from auditor.domain.ports.knowledge_retriever_port import RetrievedChunk


@dataclass(frozen=True)
class SemanticAnalysisContext:
    entity_id: str
    entity_type: EntityType
    plain_values: dict
    schema: dict
    structural_violations: tuple[Violation, ...]
    knowledge_chunks: tuple["RetrievedChunk", ...]


@dataclass(frozen=True)
class SemanticAnalysisResult:
    """`analysis_unavailable=True` sempre vem acompanhado de
    `violations=()` e `recommendations=()` — nunca uma mistura de
    resultado parcial confiavel com o resto descartado; se a saida do
    modelo nao valida, nada dela e' usado (secao 1 do spec)."""

    violations: tuple[Violation, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    analysis_unavailable: bool = False
    # Fase 10 (.cursor/specs/fase10.spec.md, secao 3.4): metadados de
    # custo de inferencia, nao participa da invariante abaixo — presente
    # mesmo quando analysis_unavailable=True (a chamada ainda gastou
    # tempo/tokens, mesmo sem produzir saida valida).
    usage: SemanticAnalysisUsage | None = None

    def __post_init__(self) -> None:
        if self.analysis_unavailable and (self.violations or self.recommendations):
            raise InconsistentSemanticAnalysisResultError(
                "SemanticAnalysisResult.analysis_unavailable=True nunca pode "
                "vir acompanhado de violations/recommendations nao vazios."
            )


class SemanticAnalyzerPort(Protocol):
    async def analyze(self, ctx: SemanticAnalysisContext) -> SemanticAnalysisResult:
        """Nunca levanta excecao para fora — falha de rede, timeout ou saida
        do modelo que nao valida vira `analysis_unavailable=True` (secao 2).
        Uma falha do SLM nunca derruba o AuditRun inteiro: e' uma
        degradacao silenciosa e explicita, nao uma
        ContextBrokerUnavailableError (Fase 4) — o Nivel 1 ja' persistiu um
        resultado valido antes de o Nivel 2 sequer ser chamado (secao 4)."""
        ...
