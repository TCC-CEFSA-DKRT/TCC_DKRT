from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_selfhosted_accounts, get_settings
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccount
from auditor.interfaces.rest import app as app_module

_SAAS = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k" * 32)
_SELFHOSTED_NO_KEY = Settings(_env_file=None)
_SELFHOSTED_WITH_KEY = Settings(_env_file=None, broker_api_key_encryption_keys="k" * 32)

_TENANT_A = Tenant(fiware_service="tenant_a", fiware_service_path="/")


def _account(tenant: Tenant, broker_url: str = "https://orion.example.com") -> TenantAccount:
    return TenantAccount(
        tenant=tenant,
        broker_url=broker_url,
        broker_api_key="chave-antiga",
        login_email=None,
        password_hash=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class _FakeAccounts:
    def __init__(self, account: TenantAccount | None = None):
        self._account = account
        self.create_calls: list[tuple] = []
        self.replace_calls: list[tuple] = []

    async def get_single(self) -> TenantAccount | None:
        return self._account

    async def create(self, tenant, broker_url, broker_api_key=None, **kwargs) -> None:
        self.create_calls.append((tenant, broker_url, broker_api_key))
        self._account = _account(tenant, broker_url)

    async def replace_tenant(self, old_tenant, new_tenant, broker_url, broker_api_key) -> None:
        self.replace_calls.append((old_tenant, new_tenant, broker_url, broker_api_key))
        self._account = _account(new_tenant, broker_url)


def _client(monkeypatch, settings: Settings, accounts=None) -> httpx.AsyncClient:
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    app = app_module.create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    if accounts is not None:
        app.dependency_overrides[get_selfhosted_accounts] = lambda: accounts
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


class TestNotMountedInSaas:
    @pytest.mark.asyncio
    async def test_get_config_is_404_in_saas(self, monkeypatch):
        async with _client(monkeypatch, _SAAS) as client:
            response = await client.get("/config")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_put_config_is_404_in_saas(self, monkeypatch):
        async with _client(monkeypatch, _SAAS) as client:
            response = await client.put(
                "/config",
                json={"broker_url": "https://orion.example.com", "fiware_service": "openiot"},
            )

        assert response.status_code == 404


class TestGetConfig:
    @pytest.mark.asyncio
    async def test_no_row_prefills_from_settings_and_is_not_configured(self, monkeypatch):
        settings = Settings(
            _env_file=None,
            broker_api_key_encryption_keys="k" * 32,
            fiware_broker_url="http://orion:1026",
            fiware_service="openiot",
            fiware_service_path="/",
        )
        async with _client(monkeypatch, settings, accounts=_FakeAccounts(None)) as client:
            response = await client.get("/config")

        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is False
        assert body["broker_url"] == "http://orion:1026"
        assert body["fiware_service"] == "openiot"
        assert body["fiware_service_path"] == "/"
        assert "broker_api_key" not in body

    @pytest.mark.asyncio
    async def test_saved_row_is_configured_and_never_returns_the_api_key(self, monkeypatch):
        account = _account(_TENANT_A, "https://orion-saved.example.com")
        async with _client(
            monkeypatch, _SELFHOSTED_WITH_KEY, accounts=_FakeAccounts(account)
        ) as client:
            response = await client.get("/config")

        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["broker_url"] == "https://orion-saved.example.com"
        assert body["fiware_service"] == "tenant_a"
        assert "broker_api_key" not in body

    @pytest.mark.asyncio
    async def test_without_fernet_key_is_configured_from_env(self, monkeypatch):
        async with _client(monkeypatch, _SELFHOSTED_NO_KEY) as client:
            response = await client.get("/config")

        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["broker_url"] == _SELFHOSTED_NO_KEY.fiware_broker_url
        assert body["fiware_service"] == _SELFHOSTED_NO_KEY.fiware_service


class TestPutConfig:
    @pytest.mark.asyncio
    async def test_no_row_calls_create_with_broker_api_key_none(self, monkeypatch):
        accounts = _FakeAccounts(None)
        async with _client(
            monkeypatch, _SELFHOSTED_WITH_KEY, accounts=accounts
        ) as client:
            response = await client.put(
                "/config",
                json={
                    "broker_url": "http://orion:1026",
                    "fiware_service": "openiot",
                    "fiware_service_path": "/",
                },
            )

        assert response.status_code == 200
        assert len(accounts.create_calls) == 1
        tenant, broker_url, broker_api_key = accounts.create_calls[0]
        assert tenant == Tenant(fiware_service="openiot", fiware_service_path="/")
        assert broker_url == "http://orion:1026"
        assert broker_api_key is None
        body = response.json()
        assert body["configured"] is True
        assert body["broker_url"] == "http://orion:1026"

    @pytest.mark.asyncio
    async def test_existing_row_calls_replace_tenant_with_broker_api_key_none(
        self, monkeypatch
    ):
        accounts = _FakeAccounts(_account(_TENANT_A, "https://orion-old.example.com"))
        async with _client(
            monkeypatch, _SELFHOSTED_WITH_KEY, accounts=accounts
        ) as client:
            response = await client.put(
                "/config",
                json={
                    "broker_url": "https://orion-new.example.com",
                    "fiware_service": "tenant_b",
                    "fiware_service_path": "/",
                },
            )

        assert response.status_code == 200
        assert len(accounts.replace_calls) == 1
        old_tenant, new_tenant, broker_url, broker_api_key = accounts.replace_calls[0]
        assert old_tenant == _TENANT_A
        assert new_tenant == Tenant(fiware_service="tenant_b", fiware_service_path="/")
        assert broker_url == "https://orion-new.example.com"
        assert broker_api_key is None

    @pytest.mark.asyncio
    async def test_crlf_in_fiware_service_is_422(self, monkeypatch):
        accounts = _FakeAccounts(None)
        async with _client(monkeypatch, _SELFHOSTED_WITH_KEY, accounts=accounts) as client:
            response = await client.put(
                "/config",
                json={
                    "broker_url": "http://orion:1026",
                    "fiware_service": "openiot\r\nX-Injected: 1",
                },
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_path_without_leading_slash_is_422(self, monkeypatch):
        accounts = _FakeAccounts(None)
        async with _client(monkeypatch, _SELFHOSTED_WITH_KEY, accounts=accounts) as client:
            response = await client.put(
                "/config",
                json={
                    "broker_url": "http://orion:1026",
                    "fiware_service": "openiot",
                    "fiware_service_path": "sem-barra",
                },
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_http_scheme_is_422(self, monkeypatch):
        accounts = _FakeAccounts(None)
        async with _client(monkeypatch, _SELFHOSTED_WITH_KEY, accounts=accounts) as client:
            response = await client.put(
                "/config",
                json={"broker_url": "ftp://orion:1026", "fiware_service": "openiot"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_without_fernet_key_is_503(self, monkeypatch):
        async with _client(monkeypatch, _SELFHOSTED_NO_KEY) as client:
            response = await client.put(
                "/config",
                json={"broker_url": "http://orion:1026", "fiware_service": "openiot"},
            )

        assert response.status_code == 503
