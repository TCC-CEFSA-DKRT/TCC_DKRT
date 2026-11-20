from __future__ import annotations

import httpx

from auditor.domain.ports.context_broker_port import ContextBrokerPort
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.adapter_factory import build_orion_adapter
from auditor.infrastructure.context_broker.tenant_routed_context_broker import (
    TenantRoutedContextBroker,
)
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccountRepository


class SelfHostedContextBroker(TenantRoutedContextBroker):
    def __init__(
        self,
        accounts: TenantAccountRepository,
        client: httpx.AsyncClient,
        default_broker_url: str,
        default_ngsi_version: str = "v2",
    ) -> None:
        super().__init__(accounts, client)
        self._default_broker_url = default_broker_url
        self._default_ngsi_version = default_ngsi_version

    async def _adapter_for(self, tenant: Tenant) -> ContextBrokerPort:
        account = await self._accounts.get_single()
        if account is None:
            return build_orion_adapter(
                self._default_ngsi_version, self._default_broker_url, self._client
            )
        return build_orion_adapter(
            account.ngsi_version,
            account.broker_url,
            self._client,
            api_key=account.broker_api_key,
        )
