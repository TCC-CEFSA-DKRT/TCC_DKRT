from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, MultiFernet

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.persistence.tenant_account_repository import (
    TenantAccountRepository,
)

_FERNET = MultiFernet([Fernet(Fernet.generate_key())])
_TENANT = Tenant(fiware_service="acme", fiware_service_path="/")
_OTHER_TENANT = Tenant(fiware_service="acme2", fiware_service_path="/")


class TestBrokerUrlRequiresHttpsInSaas:
    async def test_create_rejects_http_when_require_https_is_true(self):
        repository = TenantAccountRepository(None, _FERNET, require_https=True)

        with pytest.raises(ValueError, match="https://"):
            await repository.create(_TENANT, "http://orion:1026")

    async def test_update_broker_rejects_http_when_require_https_is_true(self):
        repository = TenantAccountRepository(None, _FERNET, require_https=True)

        with pytest.raises(ValueError, match="https://"):
            await repository.update_broker(_TENANT, "http://orion:1026", None)

    async def test_replace_tenant_rejects_http_before_the_delete_when_require_https_is_true(self):
        repository = TenantAccountRepository(None, _FERNET, require_https=True)

        with pytest.raises(ValueError, match="https://"):
            await repository.replace_tenant(_TENANT, _OTHER_TENANT, "http://orion:1026", None)

    def test_check_broker_url_accepts_https_when_require_https_is_true(self):
        repository = TenantAccountRepository(None, _FERNET, require_https=True)

        repository._check_broker_url("https://orion.exemplo.com")

    def test_check_broker_url_accepts_http_when_require_https_is_false(self):
        repository = TenantAccountRepository(None, _FERNET, require_https=False)

        repository._check_broker_url("http://orion:1026")
