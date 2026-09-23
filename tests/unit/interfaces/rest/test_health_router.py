"""Fase 4 — GET /health/live e GET /health/ready. Ver
.cursor/specs/fase4.spec.md, secao 4.4.
"""

from __future__ import annotations

import httpx
import pytest

from auditor.infrastructure.config.container import get_engine
from auditor.interfaces.rest.app import create_app


class _FakeConnection:
    def __init__(self, should_fail: bool):
        self._should_fail = should_fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def execute(self, *args, **kwargs):
        if self._should_fail:
            raise ConnectionRefusedError("database unreachable")
        return None


class _FakeEngine:
    def __init__(self, should_fail: bool):
        self._should_fail = should_fail

    def connect(self):
        return _FakeConnection(self._should_fail)


async def _client_with_engine(should_fail: bool):
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: _FakeEngine(should_fail)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


class TestLive:
    @pytest.mark.asyncio
    async def test_live_is_always_200_regardless_of_dependencies(self):
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/live")
        assert response.status_code == 200


class TestReady:
    @pytest.mark.asyncio
    async def test_ready_is_200_when_database_is_reachable(self):
        async with await _client_with_engine(should_fail=False) as client:
            response = await client.get("/health/ready")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ready_is_503_when_database_is_unreachable(self):
        async with await _client_with_engine(should_fail=True) as client:
            response = await client.get("/health/ready")
        assert response.status_code == 503
