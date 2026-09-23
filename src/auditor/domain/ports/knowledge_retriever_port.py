"""KnowledgeRetrieverPort — ver .cursor/specs/fase6.spec.md, secao 1.

Unico ponto que a Aplicacao (Fase 7) conhece do RAG. `retrieve()` recebe uma
string, nao um `Violation` — decisao deliberada: acopla esta porta so' ao
conceito de busca semantica, nao as formas de dado da Fase 7 (que ainda nao
existem quando esta fase e' implementada). `RetrievedChunk.similarity` fica
exposto porque a decisao de "isso e' relevante o suficiente para usar no
prompt do SLM" e' da Fase 7, nao desta porta (fase6.spec.md, secao 8, fora
de escopo).

Escopo desta fase (fase6.spec.md, topo): o RAG aqui NAO indexa o schema de
nenhum Smart Data Model especifico — isso continua vindo por busca direta e
ao vivo via SchemaCatalogPort (Fase 2). O que esta porta busca e'
conhecimento estavel, curado pelo time, sobre como julgar conformidade
semantica (convencoes, casos anotados, sinonimos, estilo de recomendacao).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class KnowledgeCategory(str, Enum):
    CONVENTION = "convention"
    ANNOTATED_CASE = "annotated_case"
    SYNONYM_GLOSSARY = "synonym_glossary"
    RECOMMENDATION_STYLE = "recommendation_style"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    category: KnowledgeCategory
    content: str
    similarity: float
    tags: tuple[str, ...]


class KnowledgeRetrieverPort(Protocol):
    async def retrieve(self, query: str, *, top_k: int = 5) -> list["RetrievedChunk"]:
        """Busca vetorial no corpus curado (secao 2 do spec). `query` e'
        texto livre — esta porta nao sabe nada sobre `Violation` nem sobre o
        dominio de auditoria; quem decide o que colocar na query e' quem
        chama (Fase 7). Resultados vem ordenados por `similarity`
        decrescente. Corpus vazio -> `[]`, nunca excecao."""
        ...
