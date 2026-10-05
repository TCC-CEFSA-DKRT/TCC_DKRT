from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_selfhosted_accounts, get_settings
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccount
from auditor.interfaces.rest import app as app_module
from auditor.interfaces.rest.access_tokens import JWT_ALGORITHM, SESSION_COOKIE_NAME

_SAAS = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k" * 32)
_SELFHOSTED_NO_KEY = Settings(_env_file=None)
_SELFHOSTED_WITH_KEY = Settings(
    _env_file=None, broker_api_key_encryption_keys="k" * 32
)

_TENANT_A = Tenant(fiware_service="tenant_a", fiware_service_path="/")


def _account(tenant: Tenant) -> TenantAccount:
    return TenantAccount(
        tenant=tenant,
        broker_url="https://orion.example.com",
        broker_api_key=None,
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


def _token(settings: Settings, tenant: Tenant = _TENANT_A, expired: bool = False) -> str:
    delta = timedelta(minutes=-5) if expired else timedelta(minutes=5)
    claims = {
        "fiware_service": tenant.fiware_service,
        "fiware_service_path": tenant.fiware_service_path,
        "exp": datetime.now(timezone.utc) + delta,
    }
    return jwt.encode(claims, settings.jwt_signing_key.get_secret_value(), algorithm=JWT_ALGORITHM)


def _client(monkeypatch, settings: Settings, accounts=None) -> httpx.AsyncClient:
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    app = app_module.create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    if accounts is not None:
        app.dependency_overrides[get_selfhosted_accounts] = lambda: accounts
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


class TestSessionSaas:
    @pytest.mark.asyncio
    async def test_no_cookie_and_no_bearer_returns_200_with_null_tenant(self, monkeypatch):
        async with _client(monkeypatch, _SAAS) as client:
            response = await client.get("/session")

        assert response.status_code == 200
        body = response.json()
        assert body["deployment_mode"] == "saas"
        assert body["tenant"] is None

    @pytest.mark.asyncio
    async def test_valid_cookie_returns_the_tenant(self, monkeypatch):
        token = _token(_SAAS)
        async with _client(monkeypatch, _SAAS) as client:
            response = await client.get(
                "/session", headers={"Cookie": f"{SESSION_COOKIE_NAME}={token}"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["tenant"] == {
            "fiware_service": "tenant_a",
            "fiware_service_path": "/",
        }

    @pytest.mark.asyncio
    async def test_expired_cookie_returns_200_with_null_tenant(self, monkeypatch):
        token = _token(_SAAS, expired=True)
        async with _client(monkeypatch, _SAAS) as client:
            response = await client.get(
                "/session", headers={"Cookie": f"{SESSION_COOKIE_NAME}={token}"}
            )

        assert response.status_code == 200
        assert response.json()["tenant"] is None


class TestSessionSelfHostedWithoutKey:
    @pytest.mark.asyncio
    async def test_tenant_comes_from_settings_env(self, monkeypatch):
        async with _client(monkeypatch, _SELFHOSTED_NO_KEY) as client:
            response = await client.get("/session")

        assert response.status_code == 200
        body = response.json()
        assert body["deployment_mode"] == "selfhosted"
        assert body["tenant"] == {
            "fiware_service": _SELFHOSTED_NO_KEY.fiware_service,
            "fiware_service_path": _SELFHOSTED_NO_KEY.fiware_service_path,
        }


class TestSessionSelfHostedWithKey:
    @pytest.mark.asyncio
    async def test_no_saved_row_returns_null_tenant(self, monkeypatch):
        async with _client(monkeypatch, _SELFHOSTED_WITH_KEY, accounts=_FakeAccounts(None)) as client:
            response = await client.get("/session")

        assert response.status_code == 200
        assert response.json()["tenant"] is None

    @pytest.mark.asyncio
    async def test_saved_row_returns_its_tenant(self, monkeypatch):
        account = _account(_TENANT_A)
        async with _client(
            monkeypatch, _SELFHOSTED_WITH_KEY, accounts=_FakeAccounts(account)
        ) as client:
            response = await client.get("/session")

        assert response.status_code == 200
        assert response.json()["tenant"] == {
            "fiware_service": "tenant_a",
            "fiware_service_path": "/",
        }

    @pytest.mark.asyncio
    async def test_saved_row_with_empty_service_returns_it_as_is(self, monkeypatch):
        account = _account(Tenant(fiware_service="", fiware_service_path="/"))
        async with _client(
            monkeypatch, _SELFHOSTED_WITH_KEY, accounts=_FakeAccounts(account)
        ) as client:
            response = await client.get("/session")

        assert response.status_code == 200
        assert response.json()["tenant"]["fiware_service"] == ""
