from __future__ import annotations

import httpx

from auditor.domain.errors import TenantBrokerNotConfiguredError
from auditor.domain.ports.context_broker_port import ContextBrokerPort, RawEntity
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccountRepository


class TenantRoutedContextBroker(ContextBrokerPort):
    def __init__(self, accounts: TenantAccountRepository, client: httpx.AsyncClient) -> None:
        self._accounts = accounts
        self._client = client

    async def _adapter_for(self, tenant: Tenant) -> OrionAdapter:
        account = await self._accounts.get_by_tenant(tenant)
        if account is None:
            raise TenantBrokerNotConfiguredError(tenant)
        return OrionAdapter(
            account.broker_url, client=self._client, api_key=account.broker_api_key
        )

    async def broker_url(self, tenant: Tenant) -> str:
        adapter = await self._adapter_for(tenant)
        return await adapter.broker_url(tenant)

    async def fetch_entities(
        self,
        tenant: Tenant,
        entity_type: EntityType | None,
        entity_id: str | None = None,
    ) -> list[RawEntity]:
        adapter = await self._adapter_for(tenant)
        return await adapter.fetch_entities(tenant, entity_type, entity_id)

    async def list_entity_types(self, tenant: Tenant) -> list[str]:
        adapter = await self._adapter_for(tenant)
        return await adapter.list_entity_types(tenant)
