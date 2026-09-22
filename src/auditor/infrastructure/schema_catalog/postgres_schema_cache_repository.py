"""PostgresSchemaCacheRepository — implementacao real de SchemaCacheRepository.
Ver .cursor/specs/fase2.spec.md, secao 3.2.

NOTA IMPORTANTE: a tabela `schema_cache` e criada aqui via SQLAlchemy
`MetaData`/`Table` diretamente (`create_table_if_not_exists`), NAO por uma
migration Alembic formal — o pipeline de migrations e trabalho da Fase 3
(.cursor/specs/fase3.spec.md). Quando a Fase 3 introduzir Alembic, esta
definicao de tabela deve virar a migration inicial que inclui `schema_cache`
(ja prevista na Parte III, 3.7, do plano geral, junto de `audit_runs` etc.).

Upsert por `entity_type` via `INSERT ... ON CONFLICT DO UPDATE` — operacao
atomica de banco, e' o que garante que dois workers salvando o mesmo
`entity_type` ao mesmo tempo nao deixem a tabela inconsistente (secao 3.2,
ultimo caso de teste).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.schema_catalog.schema_cache_repository import CachedSchemaRow

metadata = MetaData()

schema_cache_table = Table(
    "schema_cache",
    metadata,
    Column("entity_type", String, primary_key=True),
    Column("data_model_name", String, nullable=False),
    Column("schema_content", JSONB, nullable=False),
    Column("etag", String, nullable=True),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("last_checked_at", DateTime(timezone=True), nullable=False),
)


class PostgresSchemaCacheRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_table_if_not_exists(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def get(self, entity_type: EntityType) -> CachedSchemaRow | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(schema_cache_table).where(
                    schema_cache_table.c.entity_type == entity_type.value
                )
            )
            row = result.mappings().first()
        if row is None:
            return None
        return CachedSchemaRow(
            entity_type=row["entity_type"],
            data_model_name=row["data_model_name"],
            schema_content=row["schema_content"],
            etag=row["etag"],
            fetched_at=row["fetched_at"],
            last_checked_at=row["last_checked_at"],
        )

    async def save(
        self,
        entity_type: EntityType,
        data_model_name: str,
        content: dict,
        etag: str | None,
        fetched_at: datetime,
    ) -> None:
        stmt = pg_insert(schema_cache_table).values(
            entity_type=entity_type.value,
            data_model_name=data_model_name,
            schema_content=content,
            etag=etag,
            fetched_at=fetched_at,
            last_checked_at=fetched_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[schema_cache_table.c.entity_type],
            set_={
                "data_model_name": stmt.excluded.data_model_name,
                "schema_content": stmt.excluded.schema_content,
                "etag": stmt.excluded.etag,
                "fetched_at": stmt.excluded.fetched_at,
                "last_checked_at": stmt.excluded.last_checked_at,
            },
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def touch_last_checked(self, entity_type: EntityType) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                update(schema_cache_table)
                .where(schema_cache_table.c.entity_type == entity_type.value)
                .values(last_checked_at=datetime.now(timezone.utc))
            )
