from __future__ import annotations

import httpx

from auditor.domain.value_objects.broker_connection import (
    BrokerConnectionCheck,
    BrokerConnectionStatus,
)
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.orion_adapter import orion_headers
from auditor.infrastructure.context_broker.orion_ld_adapter import orion_ld_headers

CONNECTION_TEST_TIMEOUT_SECONDS = 5.0
_REFUSED_CREDENTIAL_STATUSES = {401, 403}


def _is_valid_broker_url(broker_url: str) -> bool:
    if any(character.isspace() for character in broker_url):
        return False
    try:
        url = httpx.URL(broker_url)
    except httpx.InvalidURL:
        return False
    return url.scheme in {"http", "https"} and bool(url.host)


class OrionConnectionTester:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def check(
        self,
        broker_url: str,
        tenant: Tenant,
        api_key: str | None,
        ngsi_version: str = "v2",
    ) -> BrokerConnectionCheck:
        if not _is_valid_broker_url(broker_url):
            return BrokerConnectionCheck(BrokerConnectionStatus.INVALID_URL)
        if ngsi_version == "ld":
            path, headers = "/ngsi-ld/v1/types", orion_ld_headers(tenant, api_key)
        else:
            path, headers = "/v2/types", orion_headers(tenant, api_key)
        try:
            response = await self._client.get(
                f"{broker_url.rstrip('/')}{path}",
                headers=headers,
                timeout=CONNECTION_TEST_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            return BrokerConnectionCheck(BrokerConnectionStatus.TIMEOUT)
        except (httpx.InvalidURL, httpx.UnsupportedProtocol):
            return BrokerConnectionCheck(BrokerConnectionStatus.INVALID_URL)
        except httpx.HTTPError:
            return BrokerConnectionCheck(BrokerConnectionStatus.UNREACHABLE)
        return self._classify(response)

    @staticmethod
    def _classify(response: httpx.Response) -> BrokerConnectionCheck:
        if response.status_code in _REFUSED_CREDENTIAL_STATUSES:
            return BrokerConnectionCheck(
                BrokerConnectionStatus.UNAUTHORIZED, http_status=response.status_code
            )
        if not response.is_success:
            return BrokerConnectionCheck(
                BrokerConnectionStatus.UNEXPECTED_RESPONSE, http_status=response.status_code
            )
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and "typeList" in payload:
            payload = payload["typeList"]
        if not isinstance(payload, list):
            return BrokerConnectionCheck(
                BrokerConnectionStatus.UNEXPECTED_RESPONSE, http_status=response.status_code
            )
        return BrokerConnectionCheck(
            BrokerConnectionStatus.OK,
            entity_types_count=len(payload),
            http_status=response.status_code,
        )
