"""Fase 8, secao 7 -- GET /catalog. Ver .cursor/specs/fase8.spec.md.

Mesmo padrao ASGITransport + dependency_overrides de test_audits_router.py.
Este router nao depende de tenant (o catalogo e' global), entao os testes
aqui nunca enviam _TENANT_HEADERS.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from auditor.domain.entities.entity_report import SchemaOrigin, SchemaSource
from auditor.domain.errors import SchemaUnavailableError
from auditor.domain.ports.schema_catalog_port import ResolvedSchema
from auditor.infrastructure.config.container import (
    get_catalog_index,
    get_catalog_sync_status_repository,
    get_schema_catalog,
)
from auditor.infrastructure.schema_catalog.catalog_index import CatalogModelEntry
from auditor.infrastructure.schema_catalog.catalog_sync_status_repository import (
    CatalogSyncStatus,
)
from auditor.interfaces.rest.app import create_app


class _FakeCatalogSyncStatusRepository:
    def __init__(self, status: CatalogSyncStatus | None = None):
        self._status = status

    async def get(self) -> CatalogSyncStatus | None:
        return self._status


@pytest.fixture
def fake_repository() -> _FakeCatalogSyncStatusRepository:
    return _FakeCatalogSyncStatusRepository()


@pytest.fixture
def app_and_repository(fake_repository):
    app = create_app()
    app.dependency_overrides[get_catalog_sync_status_repository] = lambda: fake_repository
    return app, fake_repository


@pytest.fixture
async def client(app_and_repository):
    app, _ = app_and_repository
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestGetCatalogStatus:
    @pytest.mark.asyncio
    async def test_no_sync_ever_attempted_returns_all_none_fields(self, client):
        response = await client.get("/catalog")

        assert response.status_code == 200
        assert response.json() == {
            "last_synced_at": None,
            "last_sync_successful": None,
            "last_sync_error": None,
            "models_count": None,
        }

    @pytest.mark.asyncio
    async def test_a_successful_sync_from_days_ago_is_shown(self, client, fake_repository):
        synced_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        fake_repository._status = CatalogSyncStatus(
            last_synced_at=synced_at,
            last_sync_successful=True,
            last_sync_error=None,
            models_count=42,
        )

        response = await client.get("/catalog")

        assert response.status_code == 200
        body = response.json()
        assert body["last_sync_successful"] is True
        assert body["models_count"] == 42
        assert body["last_synced_at"].startswith("2026-09-01")

    @pytest.mark.asyncio
    async def test_a_failed_attempt_after_a_prior_success_still_shows_the_last_successful_sync(
        self, client, fake_repository
    ):
        """CatalogSyncStatusRepository.record() nunca sobrescreve o ultimo
        sucesso com uma falha (ver seu docstring) -- este teste confirma que
        o efeito e' visivel na borda HTTP: o catalogo local (da ultima
        sincronizacao boa) continua sendo mostrado, junto com o aviso de
        que a tentativa mais recente falhou."""
        last_good = datetime(2026, 8, 20, tzinfo=timezone.utc)
        fake_repository._status = CatalogSyncStatus(
            last_synced_at=last_good,
            last_sync_successful=False,
            last_sync_error="Hugging Face Hub unreachable (403)",
            models_count=42,
        )

        response = await client.get("/catalog")

        assert response.status_code == 200
        body = response.json()
        assert body["last_sync_successful"] is False
        assert body["last_sync_error"] == "Hugging Face Hub unreachable (403)"
        # o catalogo local mostrado e' o da ultima sincronizacao BOA, nunca
        # None so' porque a tentativa mais recente falhou.
        assert body["models_count"] == 42
        assert body["last_synced_at"].startswith("2026-08-20")


class _FakeCatalogIndex:
    def __init__(self, entries: list[CatalogModelEntry]):
        self._entries = entries

    def list_models(self) -> list[CatalogModelEntry]:
        return self._entries

    def ref_for(self, subject: str, model_name: str):
        from auditor.domain.value_objects.data_model_ref import DataModelRef

        return DataModelRef(
            subject=subject,
            model_name=model_name,
            version="latest",
            schema_url=(
                f"https://raw.githubusercontent.com/smart-data-models/{subject}/"
                f"master/{model_name}/schema.json"
            ),
        )


class _FakeSchemaCatalog:
    def __init__(self, resolved: ResolvedSchema | None = None, error: Exception | None = None):
        self._resolved = resolved
        self._error = error

    async def resolve_data_model(self, entity_type):
        raise NotImplementedError

    async def fetch_schema(self, data_model) -> ResolvedSchema:
        if self._error is not None:
            raise self._error
        assert self._resolved is not None
        return self._resolved


_MODELS = [
    CatalogModelEntry(subject="dataModel.Streetlighting", model_name="Streetlight"),
    CatalogModelEntry(subject="dataModel.Streetlighting", model_name="StreetlightModel"),
    CatalogModelEntry(subject="dataModel.Weather", model_name="WeatherObserved"),
]


class TestListCatalogModels:
    """GET /catalog/models -- follow-up pos-Fase 8: a tela Catalog so
    mostrava a contagem agregada, sem lista navegavel dos modelos."""

    @pytest.mark.asyncio
    async def test_returns_every_model_with_its_subject(self, app_and_repository):
        app, _ = app_and_repository
        app.dependency_overrides[get_catalog_index] = lambda: _FakeCatalogIndex(_MODELS)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/models")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert {(item["subject"], item["model_name"]) for item in body["items"]} == {
            ("dataModel.Streetlighting", "Streetlight"),
            ("dataModel.Streetlighting", "StreetlightModel"),
            ("dataModel.Weather", "WeatherObserved"),
        }

    @pytest.mark.asyncio
    async def test_filters_by_subject(self, app_and_repository):
        app, _ = app_and_repository
        app.dependency_overrides[get_catalog_index] = lambda: _FakeCatalogIndex(_MODELS)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/models", params={"subject": "dataModel.Weather"})

        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["model_name"] == "WeatherObserved"

    @pytest.mark.asyncio
    async def test_filters_by_case_insensitive_substring_in_model_name(self, app_and_repository):
        app, _ = app_and_repository
        app.dependency_overrides[get_catalog_index] = lambda: _FakeCatalogIndex(_MODELS)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/models", params={"q": "street"})

        body = response.json()
        assert body["total"] == 2
        assert {item["model_name"] for item in body["items"]} == {"Streetlight", "StreetlightModel"}

    @pytest.mark.asyncio
    async def test_pagination_respects_page_size_and_reports_has_next(self, app_and_repository):
        app, _ = app_and_repository
        app.dependency_overrides[get_catalog_index] = lambda: _FakeCatalogIndex(_MODELS)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/models", params={"page": 1, "page_size": 2})

        body = response.json()
        assert len(body["items"]) == 2
        assert body["has_next"] is True

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/models", params={"page": 2, "page_size": 2})
        body = response.json()
        assert len(body["items"]) == 1
        assert body["has_next"] is False


class TestGetCatalogModelSchema:
    """GET /catalog/models/{model_name}/schema."""

    @pytest.mark.asyncio
    async def test_returns_the_schema_content_and_its_origin(self, app_and_repository):
        app, _ = app_and_repository
        fetched_at = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        resolved = ResolvedSchema(
            data_model=_FakeCatalogIndex([]).ref_for("dataModel.Streetlighting", "Streetlight"),
            content={"$schemaVersion": "0.1.0", "type": "object"},
            origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=fetched_at),
        )
        app.dependency_overrides[get_catalog_index] = lambda: _FakeCatalogIndex(_MODELS)
        app.dependency_overrides[get_schema_catalog] = lambda: _FakeSchemaCatalog(resolved=resolved)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/catalog/models/Streetlight/schema",
                params={"subject": "dataModel.Streetlighting"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["content"] == {"$schemaVersion": "0.1.0", "type": "object"}
        assert body["source"] == "live"
        assert body["subject"] == "dataModel.Streetlighting"
        assert body["model_name"] == "Streetlight"

    @pytest.mark.asyncio
    async def test_missing_subject_query_param_returns_422_not_500(self, app_and_repository):
        app, _ = app_and_repository
        app.dependency_overrides[get_catalog_index] = lambda: _FakeCatalogIndex(_MODELS)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/models/Streetlight/schema")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unavailable_schema_returns_404_not_500(self, app_and_repository):
        app, _ = app_and_repository
        app.dependency_overrides[get_catalog_index] = lambda: _FakeCatalogIndex(_MODELS)
        app.dependency_overrides[get_schema_catalog] = lambda: _FakeSchemaCatalog(
            error=SchemaUnavailableError("sem cache e sem rede")
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/catalog/models/Streetlight/schema",
                params={"subject": "dataModel.Streetlighting"},
            )

        assert response.status_code == 404
