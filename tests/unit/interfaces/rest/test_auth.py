"""SaaS: GET /entity-types atras de JWT (dependencies.get_tenant) e
POST /auth/login (routers/auth.py). Self-hosted: regressao dos headers e
ausencia da rota de login. Mesmo padrao ASGITransport +
dependency_overrides de test_entity_types_router.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import (
    get_context_broker,
    get_settings,
    get_tenant_account_repository,
)
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import (
    TenantAccount,
    hash_password,
)
from auditor.interfaces.rest import app as app_module
from auditor.interfaces.rest.access_tokens import JWT_ALGORITHM
from auditor.interfaces.rest.routers import auth as auth_module

_SAAS = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k" * 32)
_SELFHOSTED = Settings(_env_file=None)

_TENANT_A = Tenant(fiware_service="tenant_a", fiware_service_path="/")
_TENANT_B = Tenant(fiware_service="tenant_b", fiware_service_path="/")
_TENANT_HEADERS_B = {"Fiware-Service": "tenant_b", "Fiware-ServicePath": "/"}


class _RecordingBroker:
    def __init__(self, types=None, error=None):
        self._types = types or []
        self._error = error
        self.received_tenants: list[Tenant] = []

    async def list_entity_types(self, tenant: Tenant) -> list[str]:
        self.received_tenants.append(tenant)
        if self._error:
            raise self._error
        return self._types


class _FakeTenantAccountRepository:
    def __init__(self, accounts: dict[str, TenantAccount] | None = None):
        self._accounts = accounts or {}

    async def get_by_login_email(self, login_email: str) -> TenantAccount | None:
        return self._accounts.get(login_email.strip().lower())


def _account(tenant: Tenant, password: str) -> TenantAccount:
    return TenantAccount(
        tenant=tenant,
        broker_url="https://orion.example.com",
        broker_api_key=None,
        login_email="user@example.com",
        password_hash=hash_password(password),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _token(settings: Settings = _SAAS, tenant: Tenant = _TENANT_A) -> str:
    claims = {
        "fiware_service": tenant.fiware_service,
        "fiware_service_path": tenant.fiware_service_path,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(claims, settings.jwt_signing_key.get_secret_value(), algorithm=JWT_ALGORITHM)


def _client(monkeypatch, settings: Settings, broker=None, repository=None) -> httpx.AsyncClient:
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    app = app_module.create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    if broker is not None:
        app.dependency_overrides[get_context_broker] = lambda: broker
    if repository is not None:
        app.dependency_overrides[get_tenant_account_repository] = lambda: repository
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


class TestGetTenantSaasBorderCases:
    @pytest.mark.asyncio
    async def test_b1_no_authorization_header_is_401_even_with_fiware_service_present(
        self, monkeypatch
    ):
        broker = _RecordingBroker()
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get("/entity-types", headers=_TENANT_HEADERS_B)

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert broker.received_tenants == []

    @pytest.mark.asyncio
    async def test_b2_basic_scheme_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": "Basic abc"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b3_malformed_token_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": "Bearer abc"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b4_expired_token_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service": _TENANT_A.fiware_service,
                "fiware_service_path": _TENANT_A.fiware_service_path,
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithm=JWT_ALGORITHM,
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b5_wrong_signature_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service": _TENANT_A.fiware_service,
                "fiware_service_path": _TENANT_A.fiware_service_path,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            "outra-chave-de-32-bytes-diferente",
            algorithm=JWT_ALGORITHM,
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b6_alg_none_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service": _TENANT_A.fiware_service,
                "fiware_service_path": _TENANT_A.fiware_service_path,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            None,
            algorithm="none",
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b7_hs512_with_same_key_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service": _TENANT_A.fiware_service,
                "fiware_service_path": _TENANT_A.fiware_service_path,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithm="HS512",
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b8_missing_exp_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service": _TENANT_A.fiware_service,
                "fiware_service_path": _TENANT_A.fiware_service_path,
            },
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithm=JWT_ALGORITHM,
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b8_missing_fiware_service_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service_path": _TENANT_A.fiware_service_path,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithm=JWT_ALGORITHM,
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b9_empty_fiware_service_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service": "",
                "fiware_service_path": "/",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithm=JWT_ALGORITHM,
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b9_non_string_fiware_service_is_401(self, monkeypatch):
        broker = _RecordingBroker()
        token = jwt.encode(
            {
                "fiware_service": 123,
                "fiware_service_path": "/",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithm=JWT_ALGORITHM,
        )
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_b10_tenant_only_comes_from_the_token_never_from_headers(self, monkeypatch):
        broker = _RecordingBroker()
        token = _token(tenant=_TENANT_A)
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types",
                headers={"Authorization": f"Bearer {token}", **_TENANT_HEADERS_B},
            )

        assert response.status_code == 200
        assert broker.received_tenants == [_TENANT_A]

    @pytest.mark.asyncio
    async def test_b11_real_round_trip_login_then_entity_types(self, monkeypatch):
        broker = _RecordingBroker()
        repository = _FakeTenantAccountRepository(
            {"user@example.com": _account(_TENANT_A, "senha-correta")}
        )
        before = datetime.now(timezone.utc)
        async with _client(monkeypatch, _SAAS, broker=broker, repository=repository) as client:
            login_response = await client.post(
                "/auth/login",
                json={"login_email": "user@example.com", "password": "senha-correta"},
            )
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]

            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 200
        assert broker.received_tenants == [_TENANT_A]
        claims = jwt.decode(
            token,
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp"]},
        )
        expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
        assert before + timedelta(minutes=59) <= expires_at <= before + timedelta(minutes=61)


class TestGetTenantSelfHostedRegression:
    @pytest.mark.asyncio
    async def test_b12_bearer_header_is_ignored_tenant_comes_from_headers(self, monkeypatch):
        broker = _RecordingBroker()
        async with _client(monkeypatch, _SELFHOSTED, broker=broker) as client:
            response = await client.get(
                "/entity-types",
                headers={"Authorization": "Bearer lixo-nao-jwt", **_TENANT_HEADERS_B},
            )

        assert response.status_code == 200
        assert broker.received_tenants == [_TENANT_B]

    @pytest.mark.asyncio
    async def test_b13_login_route_does_not_exist_in_selfhosted(self, monkeypatch):
        async with _client(monkeypatch, _SELFHOSTED) as client:
            response = await client.post(
                "/auth/login", json={"login_email": "a@b.c", "password": "x"}
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_tenant_header_still_returns_401(self, monkeypatch):
        async with _client(monkeypatch, _SELFHOSTED, broker=_RecordingBroker()) as client:
            response = await client.get("/entity-types")

        assert response.status_code == 401


class TestGetEntityTypesRoutesToEachTenantsBroker:
    @pytest.mark.asyncio
    async def test_two_tenants_reach_their_own_broker_even_with_a_forged_service_header(
        self, monkeypatch
    ):
        from auditor.infrastructure.context_broker.tenant_routed_context_broker import (
            TenantRoutedContextBroker,
        )

        def _broker_account(tenant: Tenant, broker_url: str, broker_api_key: str) -> TenantAccount:
            return TenantAccount(
                tenant=tenant,
                broker_url=broker_url,
                broker_api_key=broker_api_key,
                login_email=None,
                password_hash=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

        accounts = {
            _TENANT_A: _broker_account(_TENANT_A, "https://orion-a.example.com", "k-a"),
            _TENANT_B: _broker_account(_TENANT_B, "https://orion-b.example.com", "k-b"),
        }

        class _FakeAccounts:
            def __init__(self, accounts):
                self._accounts = accounts

            async def get_by_tenant(self, tenant):
                return self._accounts.get(tenant)

        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.url.host, request.headers.get("authorization")))
            return httpx.Response(200, json=[])

        broker = TenantRoutedContextBroker(
            _FakeAccounts(accounts),
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        token_a = _token(tenant=_TENANT_A)
        token_b = _token(tenant=_TENANT_B)
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response_a = await client.get(
                "/entity-types",
                headers={"Authorization": f"Bearer {token_a}", **_TENANT_HEADERS_B},
            )
            response_b = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token_b}"}
            )

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        assert calls == [
            ("orion-a.example.com", "Bearer k-a"),
            ("orion-b.example.com", "Bearer k-b"),
        ]

    @pytest.mark.asyncio
    async def test_valid_token_with_removed_account_is_401_without_leaking_tenant_name(
        self, monkeypatch
    ):
        from auditor.infrastructure.context_broker.tenant_routed_context_broker import (
            TenantRoutedContextBroker,
        )

        class _FakeAccounts:
            async def get_by_tenant(self, tenant):
                return None

        broker = TenantRoutedContextBroker(
            _FakeAccounts(),
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
            ),
        )
        token = _token(tenant=_TENANT_A)
        async with _client(monkeypatch, _SAAS, broker=broker) as client:
            response = await client.get(
                "/entity-types", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert _TENANT_A.fiware_service not in response.text


class TestLogin:
    @pytest.mark.asyncio
    async def test_l1_correct_credentials_return_a_token_for_the_account_tenant(self, monkeypatch):
        repository = _FakeTenantAccountRepository(
            {"user@example.com": _account(_TENANT_A, "senha-correta")}
        )
        async with _client(monkeypatch, _SAAS, repository=repository) as client:
            response = await client.post(
                "/auth/login",
                json={"login_email": "user@example.com", "password": "senha-correta"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        claims = jwt.decode(
            body["access_token"],
            _SAAS.jwt_signing_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "fiware_service", "fiware_service_path"]},
        )
        assert claims["fiware_service"] == _TENANT_A.fiware_service
        assert claims["fiware_service_path"] == _TENANT_A.fiware_service_path

    @pytest.mark.asyncio
    async def test_l2_wrong_password_is_401(self, monkeypatch):
        repository = _FakeTenantAccountRepository(
            {"user@example.com": _account(_TENANT_A, "senha-correta")}
        )
        async with _client(monkeypatch, _SAAS, repository=repository) as client:
            response = await client.post(
                "/auth/login",
                json={"login_email": "user@example.com", "password": "senha-errada"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_l3_unknown_email_returns_the_same_json_body_as_wrong_password(
        self, monkeypatch
    ):
        repository = _FakeTenantAccountRepository(
            {"user@example.com": _account(_TENANT_A, "senha-correta")}
        )
        async with _client(monkeypatch, _SAAS, repository=repository) as client:
            wrong_password_response = await client.post(
                "/auth/login",
                json={"login_email": "user@example.com", "password": "senha-errada"},
            )
            unknown_email_response = await client.post(
                "/auth/login",
                json={"login_email": "ninguem@example.com", "password": "qualquer"},
            )

        assert unknown_email_response.status_code == 401
        assert unknown_email_response.json() == wrong_password_response.json()

    @pytest.mark.asyncio
    async def test_l4_unknown_email_still_runs_the_dummy_hash_path(self, monkeypatch):
        calls: list[str | None] = []
        real_password_matches = auth_module._password_matches

        def _spy(password, password_hash):
            calls.append(password_hash)
            return real_password_matches(password, password_hash)

        monkeypatch.setattr(auth_module, "_password_matches", _spy)
        repository = _FakeTenantAccountRepository({})
        async with _client(monkeypatch, _SAAS, repository=repository) as client:
            response = await client.post(
                "/auth/login",
                json={"login_email": "ninguem@example.com", "password": "qualquer"},
            )

        assert response.status_code == 401
        assert calls == [None]

    @pytest.mark.asyncio
    async def test_l5_password_over_72_bytes_is_401_not_500(self, monkeypatch):
        repository = _FakeTenantAccountRepository(
            {"user@example.com": _account(_TENANT_A, "senha-correta")}
        )
        async with _client(monkeypatch, _SAAS, repository=repository) as client:
            response = await client.post(
                "/auth/login",
                json={"login_email": "user@example.com", "password": "a" * 100},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_l6_missing_password_field_is_422(self, monkeypatch):
        repository = _FakeTenantAccountRepository({})
        async with _client(monkeypatch, _SAAS, repository=repository) as client:
            response = await client.post(
                "/auth/login", json={"login_email": "user@example.com"}
            )

        assert response.status_code == 422
