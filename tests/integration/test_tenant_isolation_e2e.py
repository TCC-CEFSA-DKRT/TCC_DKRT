from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config import container as container_module
from auditor.infrastructure.persistence.postgres_audit_repository import PostgresAuditRepository
from auditor.infrastructure.persistence.tables import create_all
from auditor.interfaces.rest.app import create_app

pytestmark = pytest.mark.integration

_PASSWORD = "senha-forte-de-teste"
_CITY_A = Tenant(fiware_service="cidade_a", fiware_service_path="/")
_CITY_B = Tenant(fiware_service="cidade_b", fiware_service_path="/")
_CITY_A_OTHER_PATH = Tenant(fiware_service="cidade_a", fiware_service_path="/outra")
_USERS = {
    "a@cidade.test": _CITY_A,
    "b@cidade.test": _CITY_B,
    "a-outra@cidade.test": _CITY_A_OTHER_PATH,
}
_CACHED = (
    container_module.get_settings,
    container_module.get_engine,
    container_module.get_tenant_account_repository,
)


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        yield pg


@pytest.fixture
async def saas(postgres_container, monkeypatch):
    for cached in _CACHED:
        cached.cache_clear()
    monkeypatch.setenv(
        "DATABASE_URL",
        postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://"),
    )
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("JWT_SIGNING_KEY", "j" * 48)
    monkeypatch.setenv("BROKER_API_KEY_ENCRYPTION_KEYS", Fernet.generate_key().decode())

    engine = container_module.get_engine()
    await create_all(engine)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE tenant_accounts, audit_runs CASCADE"))
    accounts = container_module.get_tenant_account_repository()
    for email, tenant in _USERS.items():
        await accounts.create(tenant, "https://orion.test", login_email=email, password=_PASSWORD)

    run = AuditRun.create(tenant=_CITY_A, entity_type=EntityType("Streetlight"), broker_url="https://orion.test")
    async with engine.begin() as conn:
        await PostgresAuditRepository(conn).create_run(run)

    yield create_app(), run

    for cached in _CACHED:
        cached.cache_clear()


@asynccontextmanager
async def _logged_in(app, email: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/auth/login", json={"login_email": email, "password": _PASSWORD})
        assert response.status_code == 200, response.text
        yield client


def _run_urls(run_id) -> list[str]:
    return [
        f"/audits/{run_id}",
        f"/audits/{run_id}/report.pdf",
        f"/audits/{run_id}/progress",
        f"/audits/{run_id}/stream",
    ]


@pytest.mark.asyncio
async def test_owner_sees_the_run_and_its_tenant_comes_from_the_session(saas):
    app, run = saas
    async with _logged_in(app, "a@cidade.test") as owner:
        session = (await owner.get("/session")).json()
        listed = (await owner.get("/audits")).json()["items"]
        detail = await owner.get(f"/audits/{run.id}")

    assert session["tenant"] == {"fiware_service": "cidade_a", "fiware_service_path": "/"}
    assert [item["id"] for item in listed] == [str(run.id)]
    assert detail.status_code == 200


@pytest.mark.parametrize("intruder", ["b@cidade.test", "a-outra@cidade.test"])
@pytest.mark.asyncio
async def test_another_tenant_gets_not_found_on_every_endpoint_of_the_run(saas, intruder):
    app, run = saas
    async with _logged_in(app, intruder) as client:
        statuses = {url: (await client.get(url)).status_code for url in _run_urls(run.id)}
        listed = (await client.get("/audits")).json()["items"]
        series = (await client.get("/audits/summary-over-time", params={"entity_type": "Streetlight"})).json()

    assert statuses == {url: 404 for url in statuses}
    assert listed == []
    assert series == []


@pytest.mark.asyncio
async def test_another_tenants_run_answers_exactly_like_a_run_that_does_not_exist(saas):
    app, run = saas
    async with _logged_in(app, "b@cidade.test") as client:
        foreign = [(r.status_code, r.json()) for r in [await client.get(u) for u in _run_urls(run.id)]]
        missing = [(r.status_code, r.json()) for r in [await client.get(u) for u in _run_urls(uuid4())]]

    assert foreign == missing


@pytest.mark.asyncio
async def test_forged_tenant_headers_never_reach_another_tenant(saas):
    app, run = saas
    forged = {"Fiware-Service": "cidade_a", "Fiware-ServicePath": "/"}
    async with _logged_in(app, "b@cidade.test") as client:
        response = await client.get(f"/audits/{run.id}", headers=forged)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_after_logout_the_session_no_longer_opens_the_tenant_data(saas):
    app, run = saas
    async with _logged_in(app, "a@cidade.test") as client:
        await client.post("/auth/logout")
        response = await client.get(f"/audits/{run.id}")

    assert response.status_code == 401
