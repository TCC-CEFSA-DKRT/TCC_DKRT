from __future__ import annotations

from typing import Protocol

from auditor.domain.value_objects.broker_connection import BrokerConnectionCheck
from auditor.domain.value_objects.tenant import Tenant


class BrokerConnectionTesterPort(Protocol):
    async def check(
        self,
        broker_url: str,
        tenant: Tenant,
        api_key: str | None,
        ngsi_version: str = "v2",
    ) -> BrokerConnectionCheck: ...
