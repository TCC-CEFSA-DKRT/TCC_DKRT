"""HistoricalBackendResolver -- decide QuantumLeap vs STH-Comet (ADR-0010).

Regra combinada com o usuario do projeto:
- Se o backend for informado explicitamente, usa exatamente esse.
- Caso contrario: tenta QuantumLeap primeiro; se nao encontrar dado, cai
  para o STH-Comet (legado). Escrita (subscribe/criacao de persistencia)
  SEMPRE vai para o QuantumLeap -- decisao tomada no SubscribeHandler, nao
  aqui (este resolvedor so cuida de leitura/remocao de historico existente).
"""

from typing import Any, Literal

from context_broker_agent.services.historical_data_client import HistoricalDataClient
from context_broker_agent.services.quantumleap_client import QuantumLeapClient
from context_broker_agent.services.sth_comet_client import SthCometClient

BackendName = Literal["quantumleap", "sth_comet"]


class HistoricalBackendResolver:
    def __init__(
        self,
        quantumleap: HistoricalDataClient | None = None,
        sth_comet: HistoricalDataClient | None = None,
    ) -> None:
        self.quantumleap = quantumleap or QuantumLeapClient()
        self.sth_comet = sth_comet or SthCometClient()

    def _client_for(self, backend: BackendName) -> HistoricalDataClient:
        return self.quantumleap if backend == "quantumleap" else self.sth_comet

    async def query(
        self,
        entity_id: str,
        attribute: str,
        *,
        entity_type: str | None = None,
        backend: BackendName | None = None,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], BackendName]:
        """Retorna (registros, backend_usado)."""
        if backend:
            client = self._client_for(backend)
            records = await client.query_history(entity_id, attribute, entity_type=entity_type, **kwargs)
            return records, backend

        records = await self.quantumleap.query_history(entity_id, attribute, entity_type=entity_type, **kwargs)
        if records:
            return records, "quantumleap"

        records = await self.sth_comet.query_history(entity_id, attribute, entity_type=entity_type, **kwargs)
        return records, "sth_comet"

    async def delete(
        self,
        entity_id: str,
        *,
        entity_type: str | None = None,
        attribute: str | None = None,
        backend: BackendName | None = None,
    ) -> BackendName:
        """Remove histórico. Sem backend explícito, localiza onde o dado
        vive consultando primeiro (mesma ordem do query: QuantumLeap
        primeiro) e apaga lá.

        LIMITAÇÃO: localizar "onde está" exige saber o atributo (nem
        QuantumLeap nem STH-Comet respondem "esta entidade tem histórico de
        algo?" sem apontar um atributo específico). Por isso, sem backend
        explícito, attribute é obrigatório — não dá para adivinhar.
        """
        if backend:
            client = self._client_for(backend)
            await client.delete_history(entity_id, entity_type=entity_type, attribute=attribute)
            return backend

        if not attribute:
            raise ValueError(
                "Para apagar sem informar 'backend' explicitamente, é preciso "
                "informar 'attribute' (usado para localizar onde o histórico "
                "está antes de apagar)."
            )

        records, found_in = await self.query(entity_id, attribute, entity_type=entity_type)
        if not records:
            raise ValueError(
                f"Nenhum histórico encontrado para {entity_id}.{attribute} "
                "em QuantumLeap nem STH-Comet."
            )

        client = self._client_for(found_in)
        await client.delete_history(entity_id, entity_type=entity_type, attribute=attribute)
        return found_in

    async def check_health(self) -> dict[str, dict[str, Any]]:
        return {
            "quantumleap": await self.quantumleap.check_health(),
            "sth_comet": await self.sth_comet.check_health(),
        }

        