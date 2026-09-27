from __future__ import annotations

from auditor.infrastructure.config.settings import Settings


class TestBrokerApiKeyEncryptionKeysList:
    def test_comma_separated_value_is_split_trimmed_and_order_preserved(self):
        settings = Settings(_env_file=None, broker_api_key_encryption_keys=" k2 , k1 ,")
        assert settings.broker_api_key_encryption_keys_list == ["k2", "k1"]

    def test_missing_value_yields_an_empty_list(self):
        settings = Settings(_env_file=None)
        assert settings.broker_api_key_encryption_keys_list == []

    def test_empty_value_yields_an_empty_list(self):
        settings = Settings(_env_file=None, broker_api_key_encryption_keys="")
        assert settings.broker_api_key_encryption_keys_list == []

    def test_key_never_leaks_in_repr(self):
        settings = Settings(_env_file=None, broker_api_key_encryption_keys="k2")
        assert "k2" not in repr(settings)
