"""CatalogSyncStatusRepository — persiste o resultado da ultima
sincronizacao do catalogo (CatalogIndex.sync(), Fase 2). Ver
.cursor/specs/fase8.spec.md, secao 7.

Linha unica (singleton, chave fixa "singleton") — o catalogo e' global, nao
por tenant, e so' interessa o estado mais recente. `last_synced_at`/
`models_count` sao preservados de uma tentativa BEM-SUCEDIDA anterior
mesmo quando a tentativa mais recente falha (`record()` nunca sobrescreve
o ultimo sucesso com um resultado de falha) — e' isso que permite a tela
"Catalog" mostrar "catalogo local (ultima sincronizacao bem-sucedida) com
aviso" em vez de esconder a falha ou servir dado stale como se fosse atual.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncEngine

from auditor.infrastructure.schema_catalog.catalog_index import SyncResult

_SINGLETON_ID = "singleton"

metadata = MetaData()

catalog_sync_status_table = Table(
    "catalog_sync_status",
    metadata,
    Column("id", String, primary_key=True),
    Column("last_attempted_at", DateTime(timezone=True), nullable=False),
    Column("last_attempt_successful", Boolean, nullable=False),
    Column("last_attempt_error", String, nullable=True),
    Column("last_successful_at", DateTime(timezone=True), nullable=True),
    Column("last_success_models_count", Integer, nullable=True),
)


@dataclass(frozen=True)
class CatalogSyncStatus:
    last_synced_at: datetime | None
    last_sync_successful: bool | None
    last_sync_error: str | None
    models_count: int | None


class CatalogSyncStatusRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_table_if_not_exists(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def get(self) -> CatalogSyncStatus | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(catalog_sync_status_table).where(
                        catalog_sync_status_table.c.id == _SINGLETON_ID
                    )
                )
            ).mappings().first()

        if row is None:
            return None
        return CatalogSyncStatus(
            last_synced_at=row["last_successful_at"],
            last_sync_successful=row["last_attempt_successful"],
            last_sync_error=row["last_attempt_error"],
            models_count=row["last_success_models_count"],
        )

    async def record(self, result: SyncResult, attempted_at: datetime) -> None:
        async with self._engine.begin() as conn:
            existing = (
                await conn.execute(
                    select(
                        catalog_sync_status_table.c.last_successful_at,
                        catalog_sync_status_table.c.last_success_models_count,
                    ).where(catalog_sync_status_table.c.id == _SINGLETON_ID)
                )
            ).mappings().first()

            if result.success:
                last_successful_at = attempted_at
                last_success_models_count = result.models_count
            else:
                # Preserva o ultimo sucesso — uma falha nunca apaga o
                # catalogo local ja' confirmado bom.
                last_successful_at = existing["last_successful_at"] if existing else None
                last_success_models_count = (
                    existing["last_success_models_count"] if existing else None
                )

            values = {
                "id": _SINGLETON_ID,
                "last_attempted_at": attempted_at,
                "last_attempt_successful": result.success,
                "last_attempt_error": result.reason,
                "last_successful_at": last_successful_at,
                "last_success_models_count": last_success_models_count,
            }

            if existing is None:
                await conn.execute(catalog_sync_status_table.insert().values(**values))
            else:
                await conn.execute(
                    catalog_sync_status_table.update()
                    .where(catalog_sync_status_table.c.id == _SINGLETON_ID)
                    .values(**values)
                )
