from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.self_hosted_context_broker import (
    SelfHostedContextBroker,
)
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccount

_TENANT_SAVED = Tenant(fiware_service="saved_service", fiware_service_path="/")
_TENANT_ARBITRARY = Tenant(fiware_service="arbitrary_service", fiware_service_path="/")


def _account(tenant: Tenant, broker_url: str, broker_api_key: str | None = None) -> TenantAccount:
    return TenantAccount(
        tenant=tenant,
        broker_url=broker_url,
        broker_api_key=broker_api_key,
        login_email=None,
        password_hash=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class _FakeAccounts:
    def __init__(self, account: TenantAccount | None):
        self._account = account

    async def get_single(self) -> TenantAccount | None:
        return self._account


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestWithASavedRow:
    @pytest.mark.asyncio
    async def test_uses_the_saved_row_url_and_key_ignoring_the_requested_tenant(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.url.host, request.headers.get("authorization")))
            return httpx.Response(200, json=[])

        account = _account(_TENANT_SAVED, "https://orion-saved.example.com", "chave-salva")
        broker = SelfHostedContextBroker(
            _FakeAccounts(account),
            client=_client_with_handler(handler),
            default_broker_url="http://localhost:1026",
        )

        await broker.fetch_entities(_TENANT_ARBITRARY, None)

        assert calls == [("orion-saved.example.com", "Bearer chave-salva")]

    @pytest.mark.asyncio
    async def test_broker_url_returns_the_saved_url(self):
        account = _account(_TENANT_SAVED, "https://orion-saved.example.com")
        broker = SelfHostedContextBroker(
            _FakeAccounts(account),
            client=_client_with_handler(lambda r: httpx.Response(200, json=[])),
            default_broker_url="http://localhost:1026",
        )

        assert await broker.broker_url(_TENANT_ARBITRARY) == "https://orion-saved.example.com"


class TestWithoutASavedRow:
    @pytest.mark.asyncio
    async def test_falls_back_to_the_default_broker_url(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.url.host, request.headers.get("authorization")))
            return httpx.Response(200, json=[])

        broker = SelfHostedContextBroker(
            _FakeAccounts(None),
            client=_client_with_handler(handler),
            default_broker_url="http://orion-default:1026",
        )

        await broker.fetch_entities(_TENANT_ARBITRARY, None)

        assert calls == [("orion-default", None)]

    @pytest.mark.asyncio
    async def test_broker_url_returns_the_default(self):
        broker = SelfHostedContextBroker(
            _FakeAccounts(None),
            client=_client_with_handler(lambda r: httpx.Response(200, json=[])),
            default_broker_url="http://orion-default:1026",
        )

        assert await broker.broker_url(_TENANT_ARBITRARY) == "http://orion-default:1026"
