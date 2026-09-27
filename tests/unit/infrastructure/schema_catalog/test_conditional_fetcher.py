"""Fase 2 — ConditionalSchemaFetcher. Ver .cursor/specs/fase2.spec.md,
secao 3.3.

Usa httpx.MockTransport — determinístico e sem rede real, ainda que o
comportamento assumido aqui (304 com If-None-Match) ja tenha sido confirmado
contra raw.githubusercontent.com de verdade durante a implementacao.
"""

import httpx
import pytest

from auditor.infrastructure.schema_catalog.conditional_fetcher import (
    ConditionalSchemaFetcher,
    NewContent,
    NotModified,
    SchemaFetchUnavailableError,
)

_CURRENT_ETAG = '"abc123"'
_SCHEMA_URL = "https://example.org/schema.json"


def _handler(request: httpx.Request) -> httpx.Response:
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == _CURRENT_ETAG:
        return httpx.Response(304)
    return httpx.Response(200, json={"required": ["id"]}, headers={"ETag": _CURRENT_ETAG})


def _error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("rede indisponivel")


def _make_fetcher(handler) -> ConditionalSchemaFetcher:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return ConditionalSchemaFetcher(client=client)


class TestConditionalSchemaFetcher:
    @pytest.mark.asyncio
    async def test_first_fetch_without_known_etag_returns_new_content(self):
        fetcher = _make_fetcher(_handler)
        result = await fetcher.fetch(_SCHEMA_URL, known_etag=None)

        assert isinstance(result, NewContent)
        assert result.etag == _CURRENT_ETAG
        assert result.content == {"required": ["id"]}

    @pytest.mark.asyncio
    async def test_matching_etag_returns_not_modified(self):
        fetcher = _make_fetcher(_handler)
        result = await fetcher.fetch(_SCHEMA_URL, known_etag=_CURRENT_ETAG)

        assert isinstance(result, NotModified)

    @pytest.mark.asyncio
    async def test_different_etag_returns_new_content(self):
        fetcher = _make_fetcher(_handler)
        result = await fetcher.fetch(_SCHEMA_URL, known_etag='"outro-etag-antigo"')

        assert isinstance(result, NewContent)
        assert result.etag == _CURRENT_ETAG

    @pytest.mark.asyncio
    async def test_network_error_raises_typed_exception(self):
        fetcher = _make_fetcher(_error_handler)
        with pytest.raises(SchemaFetchUnavailableError):
            await fetcher.fetch(_SCHEMA_URL, known_etag=None)
