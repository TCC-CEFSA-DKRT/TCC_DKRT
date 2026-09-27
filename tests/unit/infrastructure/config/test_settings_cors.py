"""Fase 8, secao 9 -- Settings.cors_allowed_origins_list. Ver
.cursor/specs/fase8.spec.md: o frontend Angular (ng serve, localhost:4200)
precisa de CORS liberado para chamar a API local -- este teste cobre so' o
parsing da lista (a liberacao em si e' testada via app real em
tests/unit/interfaces/rest/test_cors.py).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auditor.infrastructure.config.settings import Settings


class TestCorsWildcardGuardInSaas:
    def test_wildcard_in_saas_raises(self):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                deployment_mode="saas",
                jwt_signing_key="k" * 32,
                cors_allowed_origins="*",
            )

    def test_wildcard_among_other_origins_in_saas_raises(self):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                deployment_mode="saas",
                jwt_signing_key="k" * 32,
                cors_allowed_origins="https://app.example.com,*",
            )

    def test_wildcard_in_selfhosted_is_allowed(self):
        settings = Settings(_env_file=None, deployment_mode="selfhosted", cors_allowed_origins="*")

        assert settings.cors_allowed_origins_list == ["*"]


class TestCorsAllowedOriginsList:
    def test_default_covers_the_local_angular_dev_server(self):
        settings = Settings(_env_file=None)
        assert settings.cors_allowed_origins_list == ["http://localhost:4200"]

    def test_comma_separated_value_is_split_and_trimmed(self):
        settings = Settings(_env_file=None, cors_allowed_origins="http://a.com, http://b.com ,http://c.com")
        assert settings.cors_allowed_origins_list == ["http://a.com", "http://b.com", "http://c.com"]

    def test_empty_value_yields_an_empty_list_never_a_list_with_a_blank_string(self):
        settings = Settings(_env_file=None, cors_allowed_origins="")
        assert settings.cors_allowed_origins_list == []
