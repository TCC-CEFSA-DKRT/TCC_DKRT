from __future__ import annotations

import socket

import httpx
import pytest

from auditor.domain.value_objects.broker_connection import BrokerConnectionStatus
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.orion_connection_tester import OrionConnectionTester

pytestmark = pytest.mark.integration

_ORION_URL = "http://localhost:1026"
_TENANT = Tenant(fiware_service="auditor_config_test", fiware_service_path="/")
_ENTITY = {"id": "urn:ngsi-ld:Streetlight:config-test", "type": "Streetlight"}
_HEADERS = {"Fiware-Service": _TENANT.fiware_service, "Fiware-ServicePath": "/"}


@pytest.fixture
async def orion_with_one_type():
    async with httpx.AsyncClient() as client:
        await client.post(f"{_ORION_URL}/v2/entities", json=_ENTITY, headers=_HEADERS)
        yield
        await client.delete(f"{_ORION_URL}/v2/entities/{_ENTITY['id']}", headers=_HEADERS)


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _check(broker_url: str, tenant: Tenant = _TENANT):
    async with httpx.AsyncClient() as client:
        return await OrionConnectionTester(client).check(broker_url, tenant, None)


@pytest.mark.asyncio
async def test_real_orion_answers_with_the_types_of_the_tenant(orion_with_one_type):
    check = await _check(_ORION_URL)

    assert check.status is BrokerConnectionStatus.OK
    assert check.entity_types_count == 1


@pytest.mark.asyncio
async def test_real_orion_with_an_empty_service_still_counts_as_connected():
    check = await _check(_ORION_URL, Tenant(fiware_service="servico_sem_dados", fiware_service_path="/"))

    assert check.status is BrokerConnectionStatus.OK
    assert check.entity_types_count == 0


@pytest.mark.asyncio
async def test_a_wrong_path_on_the_orion_host_is_an_unexpected_response():
    check = await _check(f"{_ORION_URL}/caminho-errado")

    assert check.status is BrokerConnectionStatus.UNEXPECTED_RESPONSE
    assert check.http_status is not None and check.http_status >= 400


@pytest.mark.asyncio
async def test_a_port_without_orion_is_unreachable():
    check = await _check(f"http://127.0.0.1:{_closed_port()}")

    assert check.status is BrokerConnectionStatus.UNREACHABLE
