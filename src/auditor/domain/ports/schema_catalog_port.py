"""SchemaCatalogPort — ver .cursor/specs/fase2.spec.md, secao 1.

Unico ponto que a Application layer conhece. Duas operacoes separadas de
proposito: a primeira responde "esse tipo tem modelo conhecido?" (raramente
depende de rede); a segunda responde "qual o conteudo atual desse schema?"
(a pergunta que muda por natureza e precisa da politica de cache — secao 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from auditor.domain.entities.entity_report import SchemaOrigin
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType


@dataclass(frozen=True)
class ResolvedSchema:
    data_model: DataModelRef
    content: dict
    origin: SchemaOrigin


class SchemaCatalogPort(Protocol):
    async def resolve_data_model(self, entity_type: EntityType) -> DataModelRef | None:
        """Responde apenas 'existe um Smart Data Model para este tipo, e qual
        e' — nao busca o conteudo do schema."""
        ...

    async def fetch_schema(self, data_model: DataModelRef) -> ResolvedSchema:
        """Obtem o conteudo do schema, aplicando a politica de cache em duas
        camadas + verificacao condicional (secao 3 do spec da Fase 2)."""
        ...
