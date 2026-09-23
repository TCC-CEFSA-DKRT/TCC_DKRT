"""Fase 4 — ponta a ponta: POST /audits audita um tipo real no Orion do
docker-compose e GET /audits/{run_id} mostra o resultado persistido. Ver
.cursor/specs/fase4.spec.md, secao 6 ("definicao de pronto", criterio
literal do plano geral).

Requer:
- Orion do docker-compose rodando em localhost:1026 (`docker-compose up -d`)
- Docker disponivel para o Postgres descartavel (testcontainers)

Nao roda no ambiente de sandbox usado para desenvolver esta fase (sem Orion
ali). Rode localmente com:

    docker-compose up -d
    pip install -e ".[dev]"
    pytest -m integration tests/integration/test_run_audit_e2e.py -v
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from auditor.infrastructure.config import container as container_module
from auditor.infrastructure.persistence.tables import create_all
from auditor.interfaces.rest.app import create_app

pytestmark = pytest.mark.integration

_ORION_URL = "http://localhost:1026"
_TENANT_HEADERS = {"Fiware-Service": "auditor_fase4_e2e", "Fiware-ServicePath": "/"}


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        yield pg


@pytest.fixture
async def wired_app(postgres_container, monkeypatch):
    # lru_cache do composition root persiste entre testes do processo —
    # limpa tudo para que cada teste construa seus proprios engine/adapters
    # apontando para o Postgres descartavel deste modulo, nunca vazando
    # estado (ou conexoes fechadas) de outro teste/modulo.
    for cached in (
        container_module.get_settings,
        container_module.get_engine,
        container_module.get_http_client,
        container_module.get_schema_catalog,
    ):
        cached.cache_clear()

    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("FIWARE_BROKER_URL", _ORION_URL)

    await create_all(container_module.get_engine())

    yield create_app()

    for cached in (
        container_module.get_settings,
        container_module.get_engine,
        container_module.get_http_client,
        container_module.get_schema_catalog,
    ):
        cached.cache_clear()


async def _seed_entity() -> str:
    entity_id = "urn:ngsi-ld:Streetlight:e2e-1"
    async with httpx.AsyncClient() as client:
        await client.delete(
            f"{_ORION_URL}/v2/entities/{entity_id}", headers=_TENANT_HEADERS
        )  # limpa resto de execucao anterior, se houver
        resp = await client.post(
            f"{_ORION_URL}/v2/entities",
            json={
                "id": entity_id,
                "type": "Streetlight",
                "illuminanceLevel": {"type": "Number", "value": 0.5},
            },
            headers=_TENANT_HEADERS,
        )
        assert resp.status_code == 201, resp.text
    return entity_id


async def _delete_entity(entity_id: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.delete(f"{_ORION_URL}/v2/entities/{entity_id}", headers=_TENANT_HEADERS)


class TestPostThenGet:
    @pytest.mark.asyncio
    async def test_post_audits_then_get_shows_persisted_result(self, wired_app):
        entity_id = await _seed_entity()
        try:
            transport = httpx.ASGITransport(app=wired_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                create_resp = await client.post(
                    "/audits", json={"entity_type": "Streetlight"}, headers=_TENANT_HEADERS
                )
                assert create_resp.status_code == 202
                run_id = create_resp.json()["run_id"]

                # o processamento roda em BackgroundTasks depois da resposta
                # do POST — como aqui nao ha' servidor ASGI real
                # coordenando isso via ciclo de vida HTTP, aguardamos o
                # status chegar a um estado terminal por polling curto.
                final_status = None
                for _ in range(30):
                    get_resp = await client.get(f"/audits/{run_id}", headers=_TENANT_HEADERS)
                    assert get_resp.status_code == 200
                    body = get_resp.json()
                    if body["status"] in ("completed", "failed", "partial"):
                        final_status = body
                        break
                    await asyncio.sleep(0.5)

                assert final_status is not None, "run nao chegou a um status terminal a tempo"
                assert final_status["status"] == "completed"
                assert final_status["summary"]["total_entities"] == 1
                assert final_status["reports"][0]["entity_id"] == entity_id
        finally:
            await _delete_entity(entity_id)
