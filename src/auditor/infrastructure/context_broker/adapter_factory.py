"""build_orion_adapter — escolhe entre NGSI-v2 (OrionAdapter) e NGSI-LD
(OrionLdAdapter) a partir da estrutura configurada para aquele broker (ver
ADR-0023). Unico lugar que decide essa escolha -- TenantRoutedContextBroker,
SelfHostedContextBroker e o container (infrastructure/config/container.py)
chamam esta funcao em vez de instanciar o adapter concreto direto.
"""

from __future__ import annotations

import httpx

from auditor.domain.ports.context_broker_port import ContextBrokerPort
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter
from auditor.infrastructure.context_broker.orion_ld_adapter import OrionLdAdapter


def build_orion_adapter(
    ngsi_version: str,
    base_url: str,
    client: httpx.AsyncClient,
    api_key: str | None = None,
) -> ContextBrokerPort:
    if ngsi_version == "ld":
        return OrionLdAdapter(base_url, client=client, api_key=api_key)
    return OrionAdapter(base_url, client=client, api_key=api_key)
