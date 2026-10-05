"""Fase 4 — OrionAdapter contra um Orion real. Ver
.cursor/specs/fase4.spec.md, secao 2.1.

Requer o Orion do docker-compose do projeto rodando (`docker-compose up -d`
sobe `orion` em localhost:1026 — ver docker-compose.yml). Nao roda no
ambiente de sandbox usado para desenvolver esta fase (sem Orion ali) — rode
localmente com:

    docker-compose up -d
    pip install -e ".[dev]"
    pytest -m integration tests/integration/context_broker/test_orion_adapter_integration.py -v
"""

from __future__ import annotations

import httpx
import pytest

from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter

pytestmark = pytest.mark.integration

_ORION_URL = "http://localhost:1026"
_TENANT = Tenant(fiware_service="auditor_fase4_test", fiware_service_path="/")


def _entity(entity_id: str, entity_type: str) -> dict:
    return {
        "id": entity_id,
        "type": entity_type,
        "illuminanceLevel": {"type": "Number", "value": 0.5},
    }


@pytest.fixture
async def seeded_orion():
    headers = {
        "Fiware-Service": _TENANT.fiware_service,
        "Fiware-ServicePath": _TENANT.fiware_service_path,
        "Content-Type": "application/json",
    }
    entities = [
        _entity("urn:ngsi-ld:Streetlight:t1", "Streetlight"),
        _entity("urn:ngsi-ld:Streetlight:t2", "Streetlight"),
        _entity("urn:ngsi-ld:Streetlight:t3", "Streetlight"),
        _entity("urn:ngsi-ld:AirQualityObserved:t1", "AirQualityObserved"),
    ]
    async with httpx.AsyncClient() as client:
        for entity in entities:
            resp = await client.post(f"{_ORION_URL}/v2/entities", json=entity, headers=headers)
            assert resp.status_code in (201, 422), resp.text  # 422 = ja existe de um run anterior

        yield entities

        for entity in entities:
            await client.delete(f"{_ORION_URL}/v2/entities/{entity['id']}", headers=headers)


class TestFetchEntities:
    @pytest.mark.asyncio
    async def test_filters_by_type(self, seeded_orion):
        adapter = OrionAdapter(_ORION_URL)

        result = await adapter.fetch_entities(_TENANT, EntityType("Streetlight"))

        assert {e["id"] for e in result} == {
            "urn:ngsi-ld:Streetlight:t1",
            "urn:ngsi-ld:Streetlight:t2",
            "urn:ngsi-ld:Streetlight:t3",
        }

    @pytest.mark.asyncio
    async def test_no_type_returns_entities_of_all_types(self, seeded_orion):
        adapter = OrionAdapter(_ORION_URL)

        result = await adapter.fetch_entities(_TENANT, None)

        assert {e["id"] for e in result} == {e["id"] for e in seeded_orion}

    @pytest.mark.asyncio
    async def test_entity_id_filters_to_one_entity(self, seeded_orion):
        adapter = OrionAdapter(_ORION_URL)

        result = await adapter.fetch_entities(
            _TENANT, EntityType("Streetlight"), entity_id="urn:ngsi-ld:Streetlight:t1"
        )

        assert len(result) == 1
        assert result[0]["id"] == "urn:ngsi-ld:Streetlight:t1"

    @pytest.mark.asyncio
    async def test_tenant_without_entities_returns_empty_list(self):
        adapter = OrionAdapter(_ORION_URL)
        empty_tenant = Tenant(fiware_service="tenant_with_nothing", fiware_service_path="/")

        result = await adapter.fetch_entities(empty_tenant, EntityType("Streetlight"))

        assert result == []

    @pytest.mark.asyncio
    async def test_empty_fiware_service_finds_an_entity_created_without_the_header(self):
        entity_id = "urn:ngsi-ld:Streetlight:no-tenant-1"
        entity = _entity(entity_id, "Streetlight")
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{_ORION_URL}/v2/entities", json=entity)
            assert resp.status_code in (201, 422), resp.text  # 422 = ja existe de um run anterior
            try:
                adapter = OrionAdapter(_ORION_URL)

                result = await adapter.fetch_entities(
                    Tenant(fiware_service="", fiware_service_path="/"), EntityType("Streetlight")
                )

                assert entity_id in {e["id"] for e in result}
            finally:
                await client.delete(f"{_ORION_URL}/v2/entities/{entity_id}")
