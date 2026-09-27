from __future__ import annotations

import pytest
from pydantic import ValidationError

from auditor.infrastructure.config.settings import Settings


class TestDeploymentMode:
    def test_default_is_selfhosted(self):
        settings = Settings(_env_file=None)
        assert settings.deployment_mode == "selfhosted"

    def test_saas_without_signing_key_raises(self):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, deployment_mode="saas")

    def test_saas_with_short_key_raises(self):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="REPLACE_AFTER_APPLY")

    def test_saas_with_32_byte_key_succeeds(self):
        settings = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k" * 32)
        assert settings.jwt_signing_key.get_secret_value() == "k" * 32

    def test_selfhosted_without_signing_key_succeeds(self):
        settings = Settings(_env_file=None, deployment_mode="selfhosted")
        assert settings.jwt_signing_key is None

    def test_unknown_deployment_mode_raises(self):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, deployment_mode="bogus")

    def test_zero_expiration_minutes_raises(self):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, jwt_expiration_minutes=0)

    def test_signing_key_never_leaks_in_repr(self):
        settings = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k" * 32)
        assert "k" * 32 not in repr(settings)
