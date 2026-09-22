"""ConditionalSchemaFetcher — busca condicional via ETag. Ver
.cursor/specs/fase2.spec.md, secao 3.3.

Verificado experimentalmente contra `raw.githubusercontent.com` (fonte real
dos schemas Smart Data Models): uma segunda requisicao com header
`If-None-Match: <etag da primeira resposta>` responde `304 Not Modified`,
exatamente a semantica que este componente assume.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import httpx


class SchemaFetchUnavailableError(Exception):
    """A busca (condicional ou nao) do schema falhou por rede/timeout/HTTP —
    erro tipado para que quem chama decida explicitamente cair para o cache,
    em vez de mascarar o tipo de falha."""


@dataclass(frozen=True)
class NotModified:
    """`known_etag` ainda e valido (HTTP 304) — sem corpo processado."""


@dataclass(frozen=True)
class NewContent:
    """Conteudo novo — porque mudou na fonte, ou porque `known_etag` era
    `None` (primeira busca)."""

    content: dict
    etag: str | None


FetchResult = Union[NotModified, NewContent]


class ConditionalSchemaFetcher:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def fetch(self, schema_url: str, known_etag: str | None) -> FetchResult:
        headers = {"If-None-Match": known_etag} if known_etag else {}
        try:
            response = await self._client.get(schema_url, headers=headers, timeout=10.0)
        except httpx.HTTPError as exc:
            raise SchemaFetchUnavailableError(
                f"Falha ao buscar schema em '{schema_url}': {exc}"
            ) from exc

        if response.status_code == 304:
            return NotModified()
        if response.status_code >= 400:
            raise SchemaFetchUnavailableError(
                f"Schema em '{schema_url}' respondeu HTTP {response.status_code}."
            )
        return NewContent(content=response.json(), etag=response.headers.get("etag"))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
