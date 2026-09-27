from __future__ import annotations

import httpx
import pytest
from cryptography.fernet import Fernet

from auditor.infrastructure.config import container as container_module
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter
from auditor.infrastructure.context_broker.self_hosted_context_broker import (
    SelfHostedContextBroker,
)
from auditor.infrastructure.context_broker.tenant_routed_context_broker import (
    TenantRoutedContextBroker,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    container_module.get_settings.cache_clear()
    container_module.get_engine.cache_clear()
    container_module.get_tenant_account_repository.cache_clear()
    container_module.get_broker_http_client.cache_clear()
    container_module.get_embedder.cache_clear()
    container_module.get_knowledge_retriever.cache_clear()
    yield
    container_module.get_settings.cache_clear()
    container_module.get_engine.cache_clear()
    container_module.get_tenant_account_repository.cache_clear()
    container_module.get_broker_http_client.cache_clear()
    container_module.get_embedder.cache_clear()
    container_module.get_knowledge_retriever.cache_clear()


class TestGetContextBrokerSelfHosted:
    def test_returns_an_orion_adapter_over_the_shared_http_client_without_api_key(
        self, monkeypatch
    ):
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
        monkeypatch.delenv("BROKER_API_KEY_ENCRYPTION_KEYS", raising=False)

        def _fail(*args, **kwargs):
            raise AssertionError(
                "get_tenant_account_repository nao deveria ser chamado em selfhosted"
            )

        monkeypatch.setattr(container_module, "get_tenant_account_repository", _fail)

        broker = container_module.get_context_broker()

        assert isinstance(broker, OrionAdapter)
        assert broker._client is container_module.get_http_client()
        assert broker._api_key is None

    @pytest.mark.asyncio
    async def test_broker_url_is_the_literal_fiware_broker_url_setting(self, monkeypatch):
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
        monkeypatch.setenv("FIWARE_BROKER_URL", "http://orion:1026/")

        from auditor.domain.value_objects.tenant import Tenant

        broker = container_module.get_context_broker()

        assert await broker.broker_url(Tenant(fiware_service="openiot")) == "http://orion:1026/"


class TestGetContextBrokerSelfHostedWithEncryptionKey:
    def test_returns_a_self_hosted_context_broker_when_a_fernet_key_is_configured(
        self, monkeypatch
    ):
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", Fernet.generate_key().decode())

        broker = container_module.get_context_broker()

        assert isinstance(broker, SelfHostedContextBroker)
        assert broker._client is container_module.get_http_client()

    def test_uses_fiware_broker_url_as_the_default_broker_url(self, monkeypatch):
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", Fernet.generate_key().decode())
        monkeypatch.setenv("FIWARE_BROKER_URL", "http://orion-default:1026")

        broker = container_module.get_context_broker()

        assert broker._default_broker_url == "http://orion-default:1026"


class TestGetContextBrokerSaas:
    def test_returns_a_tenant_routed_context_broker_over_its_own_client(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
        monkeypatch.setenv("JWT_SIGNING_KEY", "k" * 32)
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", Fernet.generate_key().decode())

        broker = container_module.get_context_broker()

        assert isinstance(broker, TenantRoutedContextBroker)
        assert broker._client is container_module.get_broker_http_client()
        assert broker._client is not container_module.get_http_client()

    def test_raises_when_encryption_keys_are_missing(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
        monkeypatch.setenv("JWT_SIGNING_KEY", "k" * 32)
        monkeypatch.delenv("BROKER_API_KEY_ENCRYPTION_KEYS", raising=False)

        with pytest.raises(RuntimeError):
            container_module.get_context_broker()


class TestGetBrokerHttpClient:
    def test_does_not_follow_redirects(self):
        assert container_module.get_broker_http_client().follow_redirects is False

    def test_does_not_retain_cookies_across_calls(self):
        client = container_module.get_broker_http_client()
        client.cookies.extract_cookies(
            httpx.Response(
                200,
                headers={"set-cookie": "s=A; Path=/"},
                request=httpx.Request("GET", "https://p.example.com/"),
            )
        )

        assert len(client.cookies) == 0


class TestGetRunAuditUseCaseSmoke:
    def test_builds_without_error_in_selfhosted(self, monkeypatch):
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)

        container_module.get_run_audit_use_case()

    def test_builds_without_error_in_saas(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
        monkeypatch.setenv("JWT_SIGNING_KEY", "k" * 32)
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", Fernet.generate_key().decode())

        container_module.get_run_audit_use_case()
