from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest

from auditor.domain.value_objects.broker_connection import BrokerConnectionStatus
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker import orion_connection_tester as tester_module
from auditor.infrastructure.context_broker.orion_connection_tester import OrionConnectionTester

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/cidade")


@dataclass
class _BrokerOnLocalhost:
    url: str
    status: int = 200
    body: bytes = b"[]"
    content_type: str = "application/json"
    never_answers: bool = False
    requests: list[dict] = field(default_factory=list)


async def _serve(broker: _BrokerOnLocalhost, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    head = await reader.readuntil(b"\r\n\r\n")
    request_line, *header_lines = head.decode("latin-1").split("\r\n")
    headers = dict(line.split(": ", 1) for line in header_lines if ": " in line)
    broker.requests.append({"line": request_line, "headers": {k.lower(): v for k, v in headers.items()}})
    if broker.never_answers:
        await asyncio.sleep(10)
        return
    writer.write(
        f"HTTP/1.1 {broker.status} X\r\nContent-Type: {broker.content_type}\r\n"
        f"Content-Length: {len(broker.body)}\r\nConnection: close\r\n\r\n".encode()
        + broker.body
    )
    await writer.drain()
    writer.close()


@pytest.fixture
async def broker() -> AsyncIterator[_BrokerOnLocalhost]:
    state = _BrokerOnLocalhost(url="")
    server = await asyncio.start_server(lambda r, w: _serve(state, r, w), "127.0.0.1", 0)
    state.url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    yield state
    server.close()


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _check(broker_url: str, api_key: str | None = None):
    async with httpx.AsyncClient() as client:
        return await OrionConnectionTester(client).check(broker_url, _TENANT, api_key)


class TestReachableBroker:
    @pytest.mark.asyncio
    async def test_counts_the_entity_types_the_broker_returns(self, broker):
        broker.body = json.dumps([{"type": "Streetlight"}, {"type": "WeatherObserved"}]).encode()

        check = await _check(broker.url)

        assert check.status is BrokerConnectionStatus.OK
        assert check.succeeded
        assert check.entity_types_count == 2

    @pytest.mark.asyncio
    async def test_asks_orion_for_the_types_with_the_tenant_headers_and_the_key(self, broker):
        await _check(broker.url + "/", api_key="minha-chave")

        request = broker.requests[0]
        assert request["line"] == "GET /v2/types HTTP/1.1"
        assert request["headers"]["fiware-service"] == "openiot"
        assert request["headers"]["fiware-servicepath"] == "/cidade"
        assert request["headers"]["authorization"] == "Bearer minha-chave"

    @pytest.mark.asyncio
    async def test_sends_no_authorization_header_without_a_key(self, broker):
        await _check(broker.url)

        assert "authorization" not in broker.requests[0]["headers"]


class TestInvalidUrl:
    @pytest.mark.parametrize(
        "broker_url", ["localhost:1026", "ftp://orion:1026", "http://", "", "http://exa mple:1026"]
    )
    @pytest.mark.asyncio
    async def test_is_reported_without_sending_any_request(self, broker, broker_url):
        check = await _check(broker_url)

        assert check.status is BrokerConnectionStatus.INVALID_URL
        assert broker.requests == []


class TestBrokerProblems:
    @pytest.mark.asyncio
    async def test_a_port_where_nothing_listens_is_unreachable(self):
        check = await _check(f"http://127.0.0.1:{_closed_port()}")

        assert check.status is BrokerConnectionStatus.UNREACHABLE
        assert not check.succeeded

    @pytest.mark.asyncio
    async def test_a_broker_that_accepts_but_never_answers_is_a_timeout(self, broker, monkeypatch):
        monkeypatch.setattr(tester_module, "CONNECTION_TEST_TIMEOUT_SECONDS", 0.3)
        broker.never_answers = True

        check = await _check(broker.url)

        assert check.status is BrokerConnectionStatus.TIMEOUT

    @pytest.mark.parametrize("http_status", [401, 403])
    @pytest.mark.asyncio
    async def test_refused_credential_keeps_the_http_status(self, broker, http_status):
        broker.status = http_status
        broker.body = b'{"error": "Unauthorized"}'

        check = await _check(broker.url, api_key="chave-errada")

        assert check.status is BrokerConnectionStatus.UNAUTHORIZED
        assert check.http_status == http_status

    @pytest.mark.asyncio
    async def test_an_address_that_is_not_an_orion_is_an_unexpected_response(self, broker):
        broker.status = 404
        broker.body = b"Not Found"
        broker.content_type = "text/plain"

        check = await _check(broker.url)

        assert check.status is BrokerConnectionStatus.UNEXPECTED_RESPONSE
        assert check.http_status == 404

    @pytest.mark.asyncio
    async def test_a_page_that_answers_200_but_is_not_a_list_of_types_is_an_unexpected_response(
        self, broker
    ):
        broker.body = b"<html>ok</html>"
        broker.content_type = "text/html"

        check = await _check(broker.url)

        assert check.status is BrokerConnectionStatus.UNEXPECTED_RESPONSE
        assert check.http_status == 200
