"""Fase 2 — PostgresSchemaCacheRepository. Ver .cursor/specs/fase2.spec.md,
secao 3.2.

Requer Docker (testcontainers sobe um Postgres descartavel para os testes).
Nao roda no ambiente de sandbox usado para desenvolver esta fase (sem acesso
a Docker dali) — rode localmente com:

    pip install -e ".[dev]"
    pytest -m integration tests/integration/schema_catalog/test_postgres_schema_cache_repository.py -v
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.schema_catalog.postgres_schema_cache_repository import (
    PostgresSchemaCacheRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture
async def repository(postgres_container):
    sync_url = postgres_container.get_connection_url()  # postgresql+psycopg2://...
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    engine = create_async_engine(async_url)
    repo = PostgresSchemaCacheRepository(engine)
    await repo.create_table_if_not_exists()
    yield repo
    await engine.dispose()


class TestGet:
    @pytest.mark.asyncio
    async def test_missing_row_returns_none(self, repository):
        result = await repository.get(EntityType("Streetlight"))
        assert result is None


class TestSaveUpsert:
    @pytest.mark.asyncio
    async def test_save_twice_upserts_instead_of_duplicating(self, repository):
        entity_type = EntityType("Streetlight")
        first_fetch = datetime(2026, 1, 1, tzinfo=timezone.utc)
        second_fetch = datetime(2026, 2, 1, tzinfo=timezone.utc)

        await repository.save(
            entity_type=entity_type,
            data_model_name="Streetlight",
            content={"required": ["id"]},
            etag='"e1"',
            fetched_at=first_fetch,
        )
        await repository.save(
            entity_type=entity_type,
            data_model_name="Streetlight",
            content={"required": ["id", "type"]},
            etag='"e2"',
            fetched_at=second_fetch,
        )

        row = await repository.get(entity_type)
        assert row is not None
        assert row.schema_content == {"required": ["id", "type"]}
        assert row.etag == '"e2"'
        assert row.fetched_at == second_fetch


class TestTouchLastChecked:
    @pytest.mark.asyncio
    async def test_touch_updates_last_checked_without_changing_content(self, repository):
        entity_type = EntityType("Streetlight")
        fetched_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await repository.save(
            entity_type=entity_type,
            data_model_name="Streetlight",
            content={"required": ["id"]},
            etag='"e1"',
            fetched_at=fetched_at,
        )

        before = await repository.get(entity_type)
        await repository.touch_last_checked(entity_type)
        after = await repository.get(entity_type)

        assert after.schema_content == before.schema_content
        assert after.etag == before.etag
        assert after.last_checked_at >= before.last_checked_at


class TestConcurrentSaves:
    @pytest.mark.asyncio
    async def test_concurrent_saves_for_same_entity_type_do_not_corrupt_row(
        self, postgres_container
    ):
        import asyncio

        sync_url = postgres_container.get_connection_url()
        async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        engine = create_async_engine(async_url)
        repo = PostgresSchemaCacheRepository(engine)
        await repo.create_table_if_not_exists()

        entity_type = EntityType("Streetlight")

        async def _save(version: int) -> None:
            await repo.save(
                entity_type=entity_type,
                data_model_name="Streetlight",
                content={"version": version},
                etag=f'"e{version}"',
                fetched_at=datetime(2026, 1, version % 27 + 1, tzinfo=timezone.utc),
            )

        await asyncio.gather(*(_save(i) for i in range(1, 11)))

        row = await repo.get(entity_type)
        assert row is not None
        assert row.schema_content["version"] in range(1, 11)  # uma unica linha, valor consistente

        await engine.dispose()
