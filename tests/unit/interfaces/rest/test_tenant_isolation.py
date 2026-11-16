from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from auditor.domain.entities.audit_run import AuditRun, RunStatus
from auditor.domain.ports.audit_repository_port import AuditRunSummaryView, Page
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_settings, get_unit_of_work
from auditor.infrastructure.config.settings import Settings
from auditor.interfaces.rest import app as app_module
from auditor.interfaces.rest.access_tokens import SESSION_COOKIE_NAME, issue_access_token

_SAAS = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k" * 32)
_OWNER = Tenant(fiware_service="cidade_a", fiware_service_path="/")
_INTRUDER = Tenant(fiware_service="cidade_b", fiware_service_path="/")
_SAME_SERVICE_OTHER_PATH = Tenant(fiware_service="cidade_a", fiware_service_path="/outra")
_STREETLIGHT = EntityType("Streetlight")


class _RepositoryScopedByTenant:
    def __init__(self, runs: list[AuditRun]):
        self._runs = runs

    def _visible(self, tenant: Tenant) -> list[AuditRun]:
        return [run for run in self._runs if run.tenant == tenant]

    async def get_by_id(self, run_id, tenant):
        return next((run for run in self._visible(tenant) if run.id == run_id), None)

    async def count_reports(self, run_id, tenant):
        return 0

    async def list_runs(self, tenant, filters):
        items = [_summary(run) for run in self._visible(tenant)]
        return Page(items=items, page=filters.page, page_size=filters.page_size, total=len(items))

    async def list_run_summaries_over_time(self, tenant, entity_type):
        return [_summary(run) for run in self._visible(tenant) if run.entity_type == entity_type]


def _summary(run: AuditRun) -> AuditRunSummaryView:
    return AuditRunSummaryView(
        id=run.id,
        tenant=run.tenant,
        entity_type=run.entity_type,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        summary=run.summary,
        broker_url=run.broker_url,
    )


class _UnitOfWork:
    def __init__(self, repository):
        self.audits = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


@pytest.fixture
def owners_run() -> AuditRun:
    run = AuditRun.create(tenant=_OWNER, entity_type=_STREETLIGHT, broker_url="https://orion.a")
    run.status = RunStatus.COMPLETED
    return run


@pytest.fixture
def login_as(monkeypatch, owners_run):
    monkeypatch.setattr(app_module, "get_settings", lambda: _SAAS)
    app = app_module.create_app()
    app.dependency_overrides[get_settings] = lambda: _SAAS
    app.dependency_overrides[get_unit_of_work] = lambda: _UnitOfWork(
        _RepositoryScopedByTenant([owners_run])
    )

    def _client(tenant: Tenant) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://test",
            cookies={SESSION_COOKIE_NAME: issue_access_token(tenant, _SAAS)},
        )

    return _client


def _run_urls(run_id) -> list[str]:
    return [
        f"/audits/{run_id}",
        f"/audits/{run_id}/report.pdf",
        f"/audits/{run_id}/progress",
        f"/audits/{run_id}/stream",
    ]


class TestAnotherTenantsAuditIsNotFound:
    @pytest.mark.parametrize("intruder", [_INTRUDER, _SAME_SERVICE_OTHER_PATH], ids=["outro_servico", "mesmo_servico_outro_path"])
    @pytest.mark.asyncio
    async def test_every_endpoint_of_the_run_answers_404_never_403(self, login_as, owners_run, intruder):
        async with login_as(intruder) as client:
            responses = {url: await client.get(url) for url in _run_urls(owners_run.id)}

        assert {url: r.status_code for url, r in responses.items()} == {url: 404 for url in responses}

    @pytest.mark.asyncio
    async def test_another_tenants_run_is_indistinguishable_from_a_run_that_does_not_exist(
        self, login_as, owners_run
    ):
        async with login_as(_INTRUDER) as client:
            foreign = [await client.get(url) for url in _run_urls(owners_run.id)]
            missing = [await client.get(url) for url in _run_urls(uuid4())]

        assert [r.json() for r in foreign] == [r.json() for r in missing]

    @pytest.mark.asyncio
    async def test_forged_tenant_headers_do_not_open_another_tenants_run(self, login_as, owners_run):
        forged = {"Fiware-Service": _OWNER.fiware_service, "Fiware-ServicePath": "/"}
        async with login_as(_INTRUDER) as client:
            response = await client.get(f"/audits/{owners_run.id}", headers=forged)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_the_owner_still_sees_the_run(self, login_as, owners_run):
        async with login_as(_OWNER) as client:
            response = await client.get(f"/audits/{owners_run.id}")

        assert response.status_code == 200


class TestListsOnlyShowTheSessionTenant:
    @pytest.mark.asyncio
    async def test_audit_list_does_not_include_another_tenants_runs(self, login_as, owners_run):
        async with login_as(_INTRUDER) as intruder, login_as(_OWNER) as owner:
            intruder_ids = [item["id"] for item in (await intruder.get("/audits")).json()["items"]]
            owner_ids = [item["id"] for item in (await owner.get("/audits")).json()["items"]]

        assert intruder_ids == []
        assert owner_ids == [str(owners_run.id)]

    @pytest.mark.asyncio
    async def test_dashboard_series_does_not_include_another_tenants_runs(self, login_as):
        async with login_as(_INTRUDER) as client:
            response = await client.get("/audits/summary-over-time", params={"entity_type": "Streetlight"})

        assert response.status_code == 200
        assert response.json() == []


class TestConfigurationIsNotReachableInSaas:
    @pytest.mark.parametrize(
        "method, url",
        [("GET", "/config"), ("PUT", "/config"), ("POST", "/config/test")],
    )
    @pytest.mark.asyncio
    async def test_broker_configuration_routes_do_not_exist_for_a_logged_user(self, login_as, method, url):
        async with login_as(_INTRUDER) as client:
            response = await client.request(method, url, json={})

        assert response.status_code == 404
