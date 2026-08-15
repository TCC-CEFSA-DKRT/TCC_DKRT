"""Interface abstrata para clientes de dados historicos (ADR-0003).

Isola o restante do sistema (futuro HistoryAgent, IntentRouter) da escolha de
backend de serie historica. Hoje so existe QuantumLeapClient como
implementacao, mas trocar de backend no futuro nao deveria exigir mudar
codigo fora de services/.
"""

from abc import ABC, abstractmethod
from typing import Any


class HistoricalDataClient(ABC):
    """Contrato para consulta de dados historicos de uma entidade NGSI."""

    @abstractmethod
    async def query_history(
        self,
        entity_id: str,
        attribute: str,
        *,
        last_n: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retorna a serie historica de um atributo de uma entidade.

        Cada item da lista deve ter, no minimo, {"value": ..., "index": ...}
        (timestamp ISO 8601 em "index"), independente do backend concreto.
        """

    @abstractmethod
    async def check_health(self) -> dict[str, Any]:
        """Verifica conectividade com o backend historico."""