"""Fase 4 — OrionAdapter. Ver .cursor/specs/fase4.spec.md, secao 2.1.

Usa httpx.MockTransport — sem rede real, sem Orion de verdade (esse teste
roda em qualquer ambiente). O teste de integracao contra um Orion real fica
em tests/integration/context_broker/test_orion_adapter_integration.py.
"""

from __future__ import annotations

import httpx
import pytest

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker import orion_adapter as orion_adapter_module
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestFetchEntities:
    @pytest.mark.asyncio
    async def test_returns_entities_for_a_type(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = request.url
            captured["headers"] = request.headers
            return httpx.Response(200, json=[
                {"id": "urn:1", "type": "Streetlight"},
                {"id": "urn:2", "type": "Streetlight"},
                {"id": "urn:3", "type": "Streetlight"},
            ])

        adapter = OrionAdapter("http://orion:1026", client=_client_with_handler(handler))

        result = await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

        assert len(result) == 3
        assert captured["url"].params["type"] == "Streetlight"

    @pytest.mark.asyncio
    async def test_entity_type_none_does_not_send_type_param(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json=[])

        adapter = OrionAdapter("http://orion:1026", client=_client_with_handler(handler))

        await adapter.fetch_entities(_TENANT, None)

        assert "type" not in captured["params"]

    @pytest.mark.asyncio
    async def test_entity_id_is_forwarded_as_filter(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json=[])

        adapter = OrionAdapter("http://orion:1026", client=_client_with_handler(handler))

        await adapter.fetch_entities(_TENANT, EntityType("Streetlight"), entity_id="urn:1")

        assert captured["params"]["id"] == "urn:1"

    @pytest.mark.asyncio
    async def test_no_entities_returns_empty_list_not_error(self):
        adapter = OrionAdapter(
            "http://orion:1026",
            client=_client_with_handler(lambda request: httpx.Response(200, json=[])),
        )

        result = await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

        assert result == []

    @pytest.mark.asyncio
    async def test_tenant_headers_are_sent_exactly_as_specified(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            return httpx.Response(200, json=[])

        adapter = OrionAdapter("http://orion:1026", client=_client_with_handler(handler))
        tenant = Tenant(fiware_service="smart_city", fiware_service_path="/zone/north")

        await adapter.fetch_entities(tenant, None)

        assert captured["headers"]["fiware-service"] == "smart_city"
        assert captured["headers"]["fiware-servicepath"] == "/zone/north"

    @pytest.mark.asyncio
    async def test_http_error_status_raises_context_broker_unavailable(self):
        adapter = OrionAdapter(
            "http://orion:1026",
            client=_client_with_handler(lambda request: httpx.Response(500, json={"error": "boom"})),
        )

        with pytest.raises(ContextBrokerUnavailableError):
            await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

    @pytest.mark.asyncio
    async def test_network_error_raises_context_broker_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        adapter = OrionAdapter("http://orion:1026", client=_client_with_handler(handler))

        with pytest.raises(ContextBrokerUnavailableError):
            await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

    @pytest.mark.asyncio
    async def test_paginates_when_a_full_page_comes_back(self, monkeypatch):
        monkeypatch.setattr(orion_adapter_module, "_PAGE_SIZE", 2)
        pages = [
            [{"id": "urn:1", "type": "Streetlight"}, {"id": "urn:2", "type": "Streetlight"}],
            [{"id": "urn:3", "type": "Streetlight"}],
        ]
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            page = pages[calls["n"]]
            calls["n"] += 1
            return httpx.Response(200, json=page)

        adapter = OrionAdapter("http://orion:1026", client=_client_with_handler(handler))

        result = await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

        assert len(result) == 3
        assert calls["n"] == 2
