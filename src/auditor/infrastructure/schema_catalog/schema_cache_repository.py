"""SchemaCacheRepository — contrato da camada de cache duravel (Postgres,
tabela `schema_cache`). Ver .cursor/specs/fase2.spec.md, secao 3.2.

So o Protocol e o DTO ficam aqui (zero dependencia de SQLAlchemy/asyncpg) —
assim o orquestrador (`smart_data_models_adapter.py`) pode ser testado com um
fake, sem precisar da implementacao real nem de Postgres. A implementacao
real esta em `postgres_schema_cache_repository.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from auditor.domain.value_objects.entity_type import EntityType


@dataclass(frozen=True)
class CachedSchemaRow:
    entity_type: str
    data_model_name: str
    schema_content: dict
    etag: str | None
    fetched_at: datetime
    last_checked_at: datetime


class SchemaCacheRepository(Protocol):
    async def get(self, entity_type: EntityType) -> CachedSchemaRow | None: ...

    async def save(
        self,
        entity_type: EntityType,
        data_model_name: str,
        content: dict,
        etag: str | None,
        fetched_at: datetime,
    ) -> None: ...

    async def touch_last_checked(self, entity_type: EntityType) -> None: ...
