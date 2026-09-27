from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from auditor.infrastructure.config import container as container_module
from auditor.infrastructure.persistence.tenant_account_repository import (
    TenantAccountRepository,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    container_module.get_settings.cache_clear()
    container_module.get_tenant_account_repository.cache_clear()
    container_module.get_engine.cache_clear()
    yield
    container_module.get_settings.cache_clear()
    container_module.get_tenant_account_repository.cache_clear()
    container_module.get_engine.cache_clear()


class TestGetTenantAccountRepository:
    def test_factory_raises_when_encryption_key_is_missing(self, monkeypatch):
        monkeypatch.delenv("BROKER_API_KEY_ENCRYPTION_KEYS", raising=False)

        with pytest.raises(RuntimeError):
            container_module.get_tenant_account_repository()

    def test_factory_builds_repository_when_key_is_set(self, monkeypatch):
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", Fernet.generate_key().decode())

        repository = container_module.get_tenant_account_repository()

        assert isinstance(repository, TenantAccountRepository)

    def test_factory_raises_when_keys_are_blank(self, monkeypatch):
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", " , ")

        with pytest.raises(RuntimeError):
            container_module.get_tenant_account_repository()

    def test_factory_rejects_a_malformed_key(self, monkeypatch):
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", "nao-e-uma-chave")

        with pytest.raises(ValueError):
            container_module.get_tenant_account_repository()

    def test_factory_encrypts_with_first_key_and_decrypts_with_all(self, monkeypatch):
        k1 = Fernet.generate_key().decode()
        k2 = Fernet.generate_key().decode()
        monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", f"{k2},{k1}")

        repository = container_module.get_tenant_account_repository()

        assert repository._fernet.decrypt(Fernet(k1).encrypt(b"x")) == b"x"
        token = repository._fernet.encrypt(b"y")
        assert Fernet(k2).decrypt(token) == b"y"
        with pytest.raises(InvalidToken):
            Fernet(k1).decrypt(token)


class TestGetEngine:
    def test_engine_hides_parameters_from_errors_and_logs(self):
        assert container_module.get_engine().sync_engine.hide_parameters is True
