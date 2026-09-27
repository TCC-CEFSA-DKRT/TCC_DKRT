from __future__ import annotations

import os
from unittest import mock

import pytest
from cryptography.fernet import Fernet

from auditor.infrastructure.config.settings import Settings
from auditor.interfaces.aws_lambda import _bootstrap


class _FakeSsmClient:
    def __init__(self, values):
        self._values = values
        self.calls = []

    def get_parameter(self, *, Name, WithDecryption):
        self.calls.append((Name, WithDecryption))
        return {"Parameter": {"Value": self._values[Name]}}


class _ForbiddenSsmClient:
    def get_parameter(self, *, Name, WithDecryption):
        raise AssertionError(f"SSM nao deveria ser chamado para {Name!r} em modo selfhosted")


@pytest.fixture
def isolated_environ():
    with mock.patch.dict(os.environ, {}, clear=True):
        yield os.environ


class TestBootstrapSettingsFromAws:
    def test_broker_api_key_encryption_keys_parameter_is_loaded(self, isolated_environ, monkeypatch):
        fernet_key = Fernet.generate_key().decode()
        fake_client = _FakeSsmClient({"/auditor-prod/broker-api-key-encryption-keys": fernet_key})
        monkeypatch.setattr(
            "auditor.infrastructure.config.secrets_bootstrap._default_ssm_client",
            lambda: fake_client,
        )
        isolated_environ["BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME"] = (
            "/auditor-prod/broker-api-key-encryption-keys"
        )

        _bootstrap.bootstrap_settings_from_aws()

        assert os.environ["BROKER_API_KEY_ENCRYPTION_KEYS"] == fernet_key
        assert fake_client.calls == [("/auditor-prod/broker-api-key-encryption-keys", True)]

    def test_saas_environment_produces_saas_settings(self, isolated_environ, monkeypatch):
        jwt_key = "x" * 48
        fernet_key = Fernet.generate_key().decode()
        fake_client = _FakeSsmClient(
            {
                "/auditor-prod/jwt-signing-key": jwt_key,
                "/auditor-prod/broker-api-key-encryption-keys": fernet_key,
            }
        )
        monkeypatch.setattr(
            "auditor.infrastructure.config.secrets_bootstrap._default_ssm_client",
            lambda: fake_client,
        )
        isolated_environ["DEPLOYMENT_MODE"] = "saas"
        isolated_environ["JWT_SIGNING_KEY_PARAMETER_NAME"] = "/auditor-prod/jwt-signing-key"
        isolated_environ["BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME"] = (
            "/auditor-prod/broker-api-key-encryption-keys"
        )

        _bootstrap.bootstrap_settings_from_aws()
        settings = Settings(_env_file=None)

        assert settings.deployment_mode == "saas"
        assert settings.broker_api_key_encryption_keys_list == [fernet_key]

    def test_selfhosted_regression_does_not_call_ssm(self, isolated_environ, monkeypatch):
        monkeypatch.setattr(
            "auditor.infrastructure.config.secrets_bootstrap._default_ssm_client",
            lambda: _ForbiddenSsmClient(),
        )

        _bootstrap.bootstrap_settings_from_aws()
        settings = Settings(_env_file=None)

        assert settings.deployment_mode == "selfhosted"
