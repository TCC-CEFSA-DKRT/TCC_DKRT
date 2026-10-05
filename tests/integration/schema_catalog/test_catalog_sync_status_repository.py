"""Fase 8, secao 7 -- CatalogSyncStatusRepository. Ver .cursor/specs/fase8.spec.md.

Requer Docker (Postgres via testcontainers) -- mesmo padrao dos demais
testes de integracao desta pasta/projeto. Nao roda no ambiente de sandbox
usado para desenvolver esta fase (sem acesso a Docker dali) -- rode
localmente com:

    pip install -e ".[dev]"
    pytest -m integration tests/integration/schema_catalog/test_catalog_sync_status_repository.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from auditor.infrastructure.schema_catalog.catalog_index import SyncResult
from auditor.infrastructure.schema_catalog.catalog_sync_status_repository import (
    CatalogSyncStatusRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture
async def repository(postgres_container):
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    engine = create_async_engine(async_url)
    repo = CatalogSyncStatusRepository(engine)
    await repo.create_table_if_not_exists()
    yield repo
    await engine.dispose()


class TestGetBeforeAnySync:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_sync_was_ever_recorded(self, repository):
        result = await repository.get()
        assert result is None


class TestRecordAndGetRoundTrip:
    @pytest.mark.asyncio
    async def test_a_successful_sync_round_trips_through_record_and_get(self, repository):
        attempted_at = datetime(2026, 9, 1, tzinfo=timezone.utc)

        await repository.record(
            SyncResult(success=True, models_count=42, reason=None), attempted_at=attempted_at
        )
        status = await repository.get()

        assert status is not None
        assert status.last_synced_at == attempted_at
        assert status.last_sync_successful is True
        assert status.last_sync_error is None
        assert status.models_count == 42

    @pytest.mark.asyncio
    async def test_recording_twice_updates_the_singleton_row_instead_of_duplicating(self, repository):
        first_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        second_at = datetime(2026, 9, 2, tzinfo=timezone.utc)

        await repository.record(
            SyncResult(success=True, models_count=10, reason=None), attempted_at=first_at
        )
        await repository.record(
            SyncResult(success=True, models_count=11, reason=None), attempted_at=second_at
        )
        status = await repository.get()

        assert status.last_synced_at == second_at
        assert status.models_count == 11


class TestFailedAttemptPreservesLastSuccess:
    @pytest.mark.asyncio
    async def test_a_failing_record_call_preserves_the_prior_successful_sync_fields(self, repository):
        success_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        failure_at = datetime(2026, 9, 2, tzinfo=timezone.utc)

        await repository.record(
            SyncResult(success=True, models_count=42, reason=None), attempted_at=success_at
        )
        await repository.record(
            SyncResult(success=False, models_count=None, reason="Hugging Face Hub unreachable (403)"),
            attempted_at=failure_at,
        )
        status = await repository.get()

        assert status.last_sync_successful is False
        assert status.last_sync_error == "Hugging Face Hub unreachable (403)"
        # o ultimo SUCESSO nunca e apagado por uma falha subsequente.
        assert status.last_synced_at == success_at
        assert status.models_count == 42
