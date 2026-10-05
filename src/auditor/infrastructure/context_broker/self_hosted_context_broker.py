from __future__ import annotations

import httpx

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter
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
    ) -> None:
        super().__init__(accounts, client)
        self._default_broker_url = default_broker_url

    async def _adapter_for(self, tenant: Tenant) -> OrionAdapter:
        account = await self._accounts.get_single()
        if account is None:
            return OrionAdapter(self._default_broker_url, client=self._client)
        return OrionAdapter(account.broker_url, client=self._client, api_key=account.broker_api_key)
