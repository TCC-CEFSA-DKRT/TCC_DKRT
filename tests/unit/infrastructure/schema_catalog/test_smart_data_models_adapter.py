"""Fase 2 — SmartDataModelsAdapter.fetch_schema. Ver .cursor/specs/fase2.spec.md,
secao 3.4 (politica de 6 passos).

Combina os componentes reais (InMemorySchemaCache) com fakes do repositorio e
do fetcher — exatamente como o proprio spec pede ("com mocks dos componentes
de rede"), sem precisar de Postgres nem de rede real aqui.
"""

from datetime import datetime, timezone

import pytest

from auditor.domain.entities.entity_report import SchemaSource
from auditor.domain.errors import SchemaUnavailableError
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.schema_catalog.conditional_fetcher import (
    NewContent,
    NotModified,
    SchemaFetchUnavailableError,
)
from auditor.infrastructure.schema_catalog.in_memory_cache import InMemorySchemaCache
from auditor.infrastructure.schema_catalog.schema_cache_repository import CachedSchemaRow
from auditor.infrastructure.schema_catalog.smart_data_models_adapter import SmartDataModelsAdapter

_DATA_MODEL = DataModelRef(
    subject="dataModel.Streetlighting",
    model_name="Streetlight",
    version="latest",
    schema_url="https://example.org/schema.json",
)
_FIXED_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
_DB_FETCHED_AT = datetime(2026, 5, 1, tzinfo=timezone.utc)


class _FakeCacheRepository:
    """Test double de SchemaCacheRepository — sem Postgres."""

    def __init__(self, initial_row: CachedSchemaRow | None = None) -> None:
        self.row = initial_row
        self.get_calls = 0
        self.save_calls: list[dict] = []
        self.touch_calls = 0

    async def get(self, entity_type: EntityType) -> CachedSchemaRow | None:
        self.get_calls += 1
        return self.row

    async def save(self, entity_type, data_model_name, content, etag, fetched_at) -> None:
        self.save_calls.append(
            {
                "entity_type": entity_type,
                "data_model_name": data_model_name,
                "content": content,
                "etag": etag,
                "fetched_at": fetched_at,
            }
        )
        self.row = CachedSchemaRow(
            entity_type=entity_type.value,
            data_model_name=data_model_name,
            schema_content=content,
            etag=etag,
            fetched_at=fetched_at,
            last_checked_at=fetched_at,
        )

    async def touch_last_checked(self, entity_type: EntityType) -> None:
        self.touch_calls += 1


class _FakeFetcher:
    """Test double de ConditionalSchemaFetcher — resultado ou excecao fixos."""

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls = 0

    async def fetch(self, schema_url: str, known_etag: str | None):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


def _make_adapter(cache_repository, fetcher, memory_cache=None):
    return SmartDataModelsAdapter(
        catalog_index=None,  # fetch_schema nao usa catalog_index
        memory_cache=memory_cache or InMemorySchemaCache(),
        cache_repository=cache_repository,
        fetcher=fetcher,
        clock=lambda: _FIXED_NOW,
    )


class TestMemoryHit:
    @pytest.mark.asyncio
    async def test_schema_in_memory_short_circuits_db_and_network(self):
        memory_cache = InMemorySchemaCache()
        cache_repository = _FakeCacheRepository()
        fetcher = _FakeFetcher()
        adapter = _make_adapter(cache_repository, fetcher, memory_cache)

        # popula a memoria via um primeiro fetch_schema (fluxo "tudo ausente")
        fetcher._result = NewContent(content={"required": ["id"]}, etag='"e1"')
        first = await adapter.fetch_schema(_DATA_MODEL)
        assert cache_repository.save_calls  # sanity check do setup

        cache_repository.get_calls = 0
        fetcher.calls = 0

        second = await adapter.fetch_schema(_DATA_MODEL)

        assert second is first
        assert cache_repository.get_calls == 0
        assert fetcher.calls == 0


class TestDbHitNotModified:
    @pytest.mark.asyncio
    async def test_db_present_and_not_modified_returns_live_and_touches_db(self):
        db_row = CachedSchemaRow(
            entity_type="Streetlight",
            data_model_name="Streetlight",
            schema_content={"required": ["id"]},
            etag='"e1"',
            fetched_at=_DB_FETCHED_AT,
            last_checked_at=_DB_FETCHED_AT,
        )
        cache_repository = _FakeCacheRepository(initial_row=db_row)
        fetcher = _FakeFetcher(result=NotModified())
        adapter = _make_adapter(cache_repository, fetcher)

        result = await adapter.fetch_schema(_DATA_MODEL)

        assert result.origin.source == SchemaSource.LIVE
        assert result.origin.fetched_at == _DB_FETCHED_AT
        assert result.content == {"required": ["id"]}
        assert cache_repository.touch_calls == 1
        assert cache_repository.save_calls == []


class TestDbHitChanged:
    @pytest.mark.asyncio
    async def test_db_present_but_changed_saves_new_content_as_live(self):
        db_row = CachedSchemaRow(
            entity_type="Streetlight",
            data_model_name="Streetlight",
            schema_content={"required": ["id"]},
            etag='"e1"',
            fetched_at=_DB_FETCHED_AT,
            last_checked_at=_DB_FETCHED_AT,
        )
        cache_repository = _FakeCacheRepository(initial_row=db_row)
        new_content = {"required": ["id", "type"]}
        fetcher = _FakeFetcher(result=NewContent(content=new_content, etag='"e2"'))
        adapter = _make_adapter(cache_repository, fetcher)

        result = await adapter.fetch_schema(_DATA_MODEL)

        assert result.origin.source == SchemaSource.LIVE
        assert result.origin.fetched_at == _FIXED_NOW
        assert result.content == new_content
        assert len(cache_repository.save_calls) == 1
        assert cache_repository.save_calls[0]["etag"] == '"e2"'


class TestAllLayersEmptyNetworkAvailable:
    @pytest.mark.asyncio
    async def test_fetches_fresh_saves_and_returns_live(self):
        cache_repository = _FakeCacheRepository(initial_row=None)
        content = {"required": ["id"]}
        fetcher = _FakeFetcher(result=NewContent(content=content, etag='"e1"'))
        adapter = _make_adapter(cache_repository, fetcher)

        result = await adapter.fetch_schema(_DATA_MODEL)

        assert result.origin.source == SchemaSource.LIVE
        assert result.content == content
        assert len(cache_repository.save_calls) == 1


class TestDbHitConditionalCheckUnavailable:
    @pytest.mark.asyncio
    async def test_network_down_falls_back_to_db_content_as_cache_never_live(self):
        db_row = CachedSchemaRow(
            entity_type="Streetlight",
            data_model_name="Streetlight",
            schema_content={"required": ["id"]},
            etag='"e1"',
            fetched_at=_DB_FETCHED_AT,
            last_checked_at=_DB_FETCHED_AT,
        )
        cache_repository = _FakeCacheRepository(initial_row=db_row)
        fetcher = _FakeFetcher(error=SchemaFetchUnavailableError("rede fora"))
        adapter = _make_adapter(cache_repository, fetcher)

        result = await adapter.fetch_schema(_DATA_MODEL)

        assert result.origin.source == SchemaSource.CACHE
        assert result.origin.fetched_at == _DB_FETCHED_AT
        assert result.content == {"required": ["id"]}


class TestAllLayersEmptyNetworkUnavailable:
    @pytest.mark.asyncio
    async def test_raises_schema_unavailable_error(self):
        cache_repository = _FakeCacheRepository(initial_row=None)
        fetcher = _FakeFetcher(error=SchemaFetchUnavailableError("rede fora"))
        adapter = _make_adapter(cache_repository, fetcher)

        with pytest.raises(SchemaUnavailableError):
            await adapter.fetch_schema(_DATA_MODEL)
