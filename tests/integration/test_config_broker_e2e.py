from __future__ import annotations

import socket

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from auditor.infrastructure.config import container as container_module
from auditor.infrastructure.persistence.tables import create_all
from auditor.interfaces.rest.app import create_app

pytestmark = pytest.mark.integration

_ORION_URL = "http://localhost:1026"
_CACHED = (
    container_module.get_settings,
    container_module.get_engine,
    container_module.get_tenant_account_repository,
    container_module.get_broker_http_client,
)


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        yield pg


@pytest.fixture
async def api(postgres_container, monkeypatch):
    for cached in _CACHED:
        cached.cache_clear()
    async_url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )
    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("DEPLOYMENT_MODE", "selfhosted")
    monkeypatch.setenv("FIWARE_BROKER_URL", _ORION_URL)
    monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", Fernet.generate_key().decode())

    engine = container_module.get_engine()
    await create_all(engine)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE tenant_accounts"))

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    for cached in _CACHED:
        cached.cache_clear()


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _config(broker_url: str, **extra) -> dict:
    return {"broker_url": broker_url, "fiware_service": "auditor_config_e2e", "fiware_service_path": "/", **extra}


@pytest.mark.asyncio
async def test_saves_a_broker_that_answers_and_reads_it_back(api):
    saved = await api.put("/config", json=_config(_ORION_URL))

    assert saved.status_code == 200
    assert saved.json()["connection"]["status"] == "ok"
    loaded = (await api.get("/config")).json()
    assert loaded["configured"] is True
    assert loaded["broker_url"] == _ORION_URL


@pytest.mark.asyncio
async def test_does_not_save_a_broker_that_does_not_answer(api):
    refused = await api.put("/config", json=_config(f"http://127.0.0.1:{_closed_port()}"))

    assert refused.status_code == 409
    assert refused.json()["detail"]["connection"]["status"] == "unreachable"
    assert (await api.get("/config")).json()["configured"] is False


@pytest.mark.asyncio
async def test_saves_a_failing_broker_only_with_the_explicit_confirmation(api):
    url = f"http://127.0.0.1:{_closed_port()}"

    saved = await api.put("/config", json=_config(url, save_without_connection=True))

    assert saved.status_code == 200
    assert saved.json()["connection"] is None
    assert (await api.get("/config")).json()["broker_url"] == url


@pytest.mark.asyncio
async def test_connection_test_checks_the_real_broker_without_saving(api):
    tested = await api.post("/config/test", json=_config(_ORION_URL))

    assert tested.status_code == 200
    assert tested.json()["status"] == "ok"
    assert (await api.get("/config")).json()["configured"] is False
