"""OrionLdAdapter — ver ADR-0023.

Mesmo padrao de tests/unit/infrastructure/context_broker/test_orion_adapter.py
(httpx.MockTransport, sem rede real); cobre especificamente o que o modo LD
tem de diferente do v2: endpoint, headers (NGSILD-Tenant em vez de
Fiware-Service/-ServicePath), e a normalizacao de Relationship.
"""

from __future__ import annotations

import httpx
import pytest

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker import orion_ld_adapter as orion_ld_adapter_module
from auditor.infrastructure.context_broker.orion_ld_adapter import OrionLdAdapter

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestFetchEntities:
    @pytest.mark.asyncio
    async def test_hits_the_ngsi_ld_entities_endpoint_with_json_accept_header(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["accept"] = request.headers.get("accept")
            return httpx.Response(200, json=[])

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        await adapter.fetch_entities(_TENANT, None)

        assert captured["path"] == "/ngsi-ld/v1/entities"
        assert captured["accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_sends_tenant_as_ngsild_tenant_header_not_fiware_service(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            return httpx.Response(200, json=[])

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        await adapter.fetch_entities(_TENANT, None)

        assert captured["headers"]["ngsild-tenant"] == "openiot"
        assert "fiware-service" not in captured["headers"]
        assert "fiware-servicepath" not in captured["headers"]

    @pytest.mark.asyncio
    async def test_empty_service_omits_ngsild_tenant_header(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            return httpx.Response(200, json=[])

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))
        tenant = Tenant(fiware_service="", fiware_service_path="/")

        await adapter.fetch_entities(tenant, None)

        assert "ngsild-tenant" not in captured["headers"]

    @pytest.mark.asyncio
    async def test_entity_type_and_id_are_forwarded_as_params(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json=[])

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        await adapter.fetch_entities(_TENANT, EntityType("Streetlight"), entity_id="urn:ngsi-ld:Streetlight:1")

        assert captured["params"]["type"] == "Streetlight"
        assert captured["params"]["id"] == "urn:ngsi-ld:Streetlight:1"

    @pytest.mark.asyncio
    async def test_property_and_geoproperty_pass_through_unchanged(self):
        entity = {
            "id": "urn:ngsi-ld:Streetlight:1",
            "type": "Streetlight",
            "status": {"type": "Property", "value": "ok"},
            "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [0, 0]}},
        }
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(lambda request: httpx.Response(200, json=[entity])),
        )

        result = await adapter.fetch_entities(_TENANT, None)

        assert result == [entity]

    @pytest.mark.asyncio
    async def test_relationship_object_is_normalized_into_value(self):
        entity = {
            "id": "urn:ngsi-ld:Streetlight:1",
            "type": "Streetlight",
            "controlledAsset": {"type": "Relationship", "object": "urn:ngsi-ld:Device:1"},
        }
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(lambda request: httpx.Response(200, json=[entity])),
        )

        result = await adapter.fetch_entities(_TENANT, None)

        assert result[0]["controlledAsset"]["value"] == "urn:ngsi-ld:Device:1"
        assert result[0]["controlledAsset"]["object"] == "urn:ngsi-ld:Device:1"

    @pytest.mark.asyncio
    async def test_context_field_is_stripped(self):
        entity = {
            "id": "urn:ngsi-ld:Streetlight:1",
            "type": "Streetlight",
            "@context": ["https://example.org/context.jsonld"],
            "status": {"type": "Property", "value": "ok"},
        }
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(lambda request: httpx.Response(200, json=[entity])),
        )

        result = await adapter.fetch_entities(_TENANT, None)

        assert "@context" not in result[0]

    @pytest.mark.asyncio
    async def test_paginates_when_a_full_page_comes_back(self, monkeypatch):
        monkeypatch.setattr(orion_ld_adapter_module, "_PAGE_SIZE", 2)
        pages = [
            [{"id": "urn:1", "type": "Streetlight"}, {"id": "urn:2", "type": "Streetlight"}],
            [{"id": "urn:3", "type": "Streetlight"}],
        ]
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            page = pages[calls["n"]]
            calls["n"] += 1
            return httpx.Response(200, json=page)

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        result = await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

        assert len(result) == 3
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_http_error_status_raises_context_broker_unavailable(self):
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(lambda request: httpx.Response(500, json={"error": "boom"})),
        )

        with pytest.raises(ContextBrokerUnavailableError):
            await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

    @pytest.mark.asyncio
    async def test_network_error_raises_context_broker_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        with pytest.raises(ContextBrokerUnavailableError):
            await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))


class TestApiKey:
    @pytest.mark.asyncio
    async def test_with_api_key_sends_bearer(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            return httpx.Response(200, json=[])

        adapter = OrionLdAdapter(
            "http://orion-ld:1026", client=_client_with_handler(handler), api_key="k-a"
        )

        await adapter.fetch_entities(_TENANT, None)

        assert captured["headers"]["authorization"] == "Bearer k-a"

    @pytest.mark.asyncio
    async def test_without_api_key_sends_no_authorization_header(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            return httpx.Response(200, json=[])

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        await adapter.fetch_entities(_TENANT, None)

        assert "authorization" not in captured["headers"]


class TestBrokerUrl:
    @pytest.mark.asyncio
    async def test_broker_url_returns_the_constructor_string_literally(self):
        adapter = OrionLdAdapter(
            "http://orion-ld:1026/",
            client=_client_with_handler(lambda request: httpx.Response(200, json=[])),
        )

        assert await adapter.broker_url(_TENANT) == "http://orion-ld:1026/"


class TestListEntityTypes:
    @pytest.mark.asyncio
    async def test_returns_type_names_from_a_plain_list_response(self):
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(
                lambda request: httpx.Response(200, json=["Streetlight", "AirQualityObserved"])
            ),
        )

        result = await adapter.list_entity_types(_TENANT)

        assert result == ["Streetlight", "AirQualityObserved"]

    @pytest.mark.asyncio
    async def test_returns_type_names_from_the_entitytypelist_envelope(self):
        payload = {
            "id": "urn:ngsi-ld:EntityTypeList:1",
            "type": "EntityTypeList",
            "typeList": ["Streetlight", "AirQualityObserved"],
        }
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(lambda request: httpx.Response(200, json=payload)),
        )

        result = await adapter.list_entity_types(_TENANT)

        assert result == ["Streetlight", "AirQualityObserved"]

    @pytest.mark.asyncio
    async def test_hits_the_ngsi_ld_types_endpoint(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            return httpx.Response(200, json=[])

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        await adapter.list_entity_types(_TENANT)

        assert captured["path"] == "/ngsi-ld/v1/types"

    @pytest.mark.asyncio
    async def test_no_types_returns_empty_list_not_error(self):
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(lambda request: httpx.Response(200, json=[])),
        )

        result = await adapter.list_entity_types(_TENANT)

        assert result == []

    @pytest.mark.asyncio
    async def test_http_error_status_raises_context_broker_unavailable(self):
        adapter = OrionLdAdapter(
            "http://orion-ld:1026",
            client=_client_with_handler(lambda request: httpx.Response(500, json={"error": "boom"})),
        )

        with pytest.raises(ContextBrokerUnavailableError):
            await adapter.list_entity_types(_TENANT)

    @pytest.mark.asyncio
    async def test_network_error_raises_context_broker_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        adapter = OrionLdAdapter("http://orion-ld:1026", client=_client_with_handler(handler))

        with pytest.raises(ContextBrokerUnavailableError):
            await adapter.list_entity_types(_TENANT)
