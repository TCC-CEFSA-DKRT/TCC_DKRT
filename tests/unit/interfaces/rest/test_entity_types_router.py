"""GET /entity-types. Mesmo padrao ASGITransport + dependency_overrides de
test_catalog_router.py/test_audits_router.py.
"""

from __future__ import annotations

import httpx
import pytest

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_context_broker
from auditor.interfaces.rest.app import create_app

_TENANT_HEADERS = {"Fiware-Service": "openiot", "Fiware-ServicePath": "/"}


class _FakeContextBroker:
    def __init__(self, types: list[str] | None = None, error: Exception | None = None):
        self._types = types or []
        self._error = error

    async def list_entity_types(self, tenant: Tenant) -> list[str]:
        if self._error:
            raise self._error
        return self._types


@pytest.fixture
def fake_context_broker() -> _FakeContextBroker:
    return _FakeContextBroker()


@pytest.fixture
def app_and_broker(fake_context_broker):
    app = create_app()
    app.dependency_overrides[get_context_broker] = lambda: fake_context_broker
    return app, fake_context_broker


@pytest.fixture
async def client(app_and_broker):
    app, _ = app_and_broker
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestListEntityTypes:
    @pytest.mark.asyncio
    async def test_returns_types_discovered_from_broker(self, client, fake_context_broker):
        fake_context_broker._types = ["Streetlight", "AirQualityObserved"]

        response = await client.get("/entity-types", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        assert response.json() == {
            "types": ["Streetlight", "AirQualityObserved"],
            "broker_reachable": True,
        }

    @pytest.mark.asyncio
    async def test_broker_unavailable_returns_200_with_empty_list_not_error(
        self, client, fake_context_broker
    ):
        fake_context_broker._error = ContextBrokerUnavailableError("Orion inacessivel")

        response = await client.get("/entity-types", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        assert response.json() == {"types": [], "broker_reachable": False}

    @pytest.mark.asyncio
    async def test_missing_tenant_header_returns_401(self, client):
        response = await client.get("/entity-types")

        assert response.status_code == 401
