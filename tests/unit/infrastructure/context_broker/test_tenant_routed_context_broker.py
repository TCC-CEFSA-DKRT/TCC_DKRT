from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

import httpx
import pytest

from auditor.domain.errors import TenantBrokerNotConfiguredError
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.tenant_routed_context_broker import (
    TenantRoutedContextBroker,
)
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccount

_TENANT_A = Tenant(fiware_service="tenant_a", fiware_service_path="/")
_TENANT_B = Tenant(fiware_service="tenant_b", fiware_service_path="/")


def _account(
    tenant: Tenant, broker_url: str, broker_api_key: str | None = None
) -> TenantAccount:
    return TenantAccount(
        tenant=tenant,
        broker_url=broker_url,
        broker_api_key=broker_api_key,
        login_email=None,
        password_hash=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class _FakeTenantAccountRepository:
    def __init__(self, accounts: dict[Tenant, TenantAccount], *, delay: bool = False):
        self._accounts = accounts
        self._delay = delay

    async def get_by_tenant(self, tenant: Tenant) -> TenantAccount | None:
        if self._delay:
            await asyncio.sleep(random.random() / 1000)
        return self._accounts.get(tenant)


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestRoutingPerTenant:
    @pytest.mark.asyncio
    async def test_each_tenant_reaches_its_own_host_key_and_headers(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(
                (
                    request.url.host,
                    request.headers.get("authorization"),
                    request.headers.get("fiware-service"),
                    request.headers.get("fiware-servicepath"),
                )
            )
            return httpx.Response(200, json=[])

        accounts = {
            _TENANT_A: _account(_TENANT_A, "https://orion-a.example.com", "k-a"),
            _TENANT_B: _account(_TENANT_B, "https://orion-b.example.com", "k-b"),
        }
        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository(accounts), client=_client_with_handler(handler)
        )

        await broker.fetch_entities(_TENANT_A, None)
        await broker.fetch_entities(_TENANT_B, None)

        assert calls[0] == ("orion-a.example.com", "Bearer k-a", "tenant_a", "/")
        assert calls[1] == ("orion-b.example.com", "Bearer k-b", "tenant_b", "/")

    @pytest.mark.asyncio
    async def test_account_without_api_key_sends_no_authorization_header(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers.get("authorization")
            return httpx.Response(200, json=[])

        accounts = {_TENANT_A: _account(_TENANT_A, "https://orion-a.example.com", None)}
        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository(accounts), client=_client_with_handler(handler)
        )

        await broker.fetch_entities(_TENANT_A, None)

        assert captured["authorization"] is None


class TestMissingAccount:
    @pytest.mark.asyncio
    async def test_fetch_entities_raises_without_any_http_request(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=[])

        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository({}), client=_client_with_handler(handler)
        )

        with pytest.raises(TenantBrokerNotConfiguredError):
            await broker.fetch_entities(_TENANT_A, None)

        assert calls["n"] == 0

    @pytest.mark.asyncio
    async def test_list_entity_types_raises_without_any_http_request(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=[])

        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository({}), client=_client_with_handler(handler)
        )

        with pytest.raises(TenantBrokerNotConfiguredError):
            await broker.list_entity_types(_TENANT_A)

        assert calls["n"] == 0

    @pytest.mark.asyncio
    async def test_broker_url_raises_without_any_http_request(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=[])

        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository({}), client=_client_with_handler(handler)
        )

        with pytest.raises(TenantBrokerNotConfiguredError):
            await broker.broker_url(_TENANT_A)

        assert calls["n"] == 0


class TestNoCaching:
    @pytest.mark.asyncio
    async def test_a_broker_change_between_two_calls_is_picked_up_on_the_second_call(self):
        hosts_seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts_seen.append(request.url.host)
            return httpx.Response(200, json=[])

        accounts = {_TENANT_A: _account(_TENANT_A, "https://orion-old.example.com")}
        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository(accounts), client=_client_with_handler(handler)
        )

        await broker.fetch_entities(_TENANT_A, None)
        accounts[_TENANT_A] = _account(_TENANT_A, "https://orion-new.example.com")
        await broker.fetch_entities(_TENANT_A, None)

        assert hosts_seen == ["orion-old.example.com", "orion-new.example.com"]

    @pytest.mark.asyncio
    async def test_removing_the_account_between_two_calls_fails_the_second_call(self):
        accounts = {_TENANT_A: _account(_TENANT_A, "https://orion-a.example.com")}
        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository(accounts),
            client=_client_with_handler(lambda request: httpx.Response(200, json=[])),
        )

        await broker.fetch_entities(_TENANT_A, None)
        del accounts[_TENANT_A]

        with pytest.raises(TenantBrokerNotConfiguredError):
            await broker.fetch_entities(_TENANT_A, None)


class TestServicePathIsolationOnSharedHost:
    @pytest.mark.asyncio
    async def test_same_service_different_paths_never_mix_up_keys(self):
        tenant_x_a = Tenant(fiware_service="x", fiware_service_path="/a")
        tenant_x_b = Tenant(fiware_service="x", fiware_service_path="/b")
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(
                (
                    request.headers.get("authorization"),
                    request.headers.get("fiware-service"),
                    request.headers.get("fiware-servicepath"),
                )
            )
            return httpx.Response(200, json=[])

        accounts = {
            tenant_x_a: _account(tenant_x_a, "https://orion-shared.example.com", "k-a"),
            tenant_x_b: _account(tenant_x_b, "https://orion-shared.example.com", "k-b"),
        }
        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository(accounts), client=_client_with_handler(handler)
        )

        await broker.fetch_entities(tenant_x_a, None)
        await broker.fetch_entities(tenant_x_b, None)

        assert calls[0] == ("Bearer k-a", "x", "/a")
        assert calls[1] == ("Bearer k-b", "x", "/b")


class TestConcurrentIsolation:
    @pytest.mark.asyncio
    async def test_many_interleaved_tenants_never_cross_each_others_broker(self):
        tenants = [
            Tenant(fiware_service=f"tenant_{i}", fiware_service_path="/")
            for i in range(20)
        ]
        accounts = {
            tenant: _account(
                tenant, f"https://orion-{tenant.fiware_service}.example.com", f"k-{tenant.fiware_service}"
            )
            for tenant in tenants
        }
        recorded = []

        async def handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(random.random() / 1000)
            host = request.url.host
            authorization = request.headers.get("authorization")
            fiware_service = request.headers.get("fiware-service")
            recorded.append((host, authorization, fiware_service))
            if request.url.path == "/v2/types":
                return httpx.Response(200, json=[{"type": f"Type-{fiware_service}", "attrs": {}, "count": 1}])
            return httpx.Response(
                200, json=[{"id": f"{fiware_service}:e1", "type": "Streetlight"}]
            )

        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository(accounts, delay=True),
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        async def call(i: int, tenant: Tenant):
            if i % 2 == 0:
                entities = await broker.fetch_entities(tenant, None)
                assert entities == [{"id": f"{tenant.fiware_service}:e1", "type": "Streetlight"}]
            else:
                types = await broker.list_entity_types(tenant)
                assert types == [f"Type-{tenant.fiware_service}"]

        await asyncio.gather(*(call(i, tenants[i % len(tenants)]) for i in range(200)))

        for host, authorization, fiware_service in recorded:
            assert host == f"orion-{fiware_service}.example.com"
            assert authorization == f"Bearer k-{fiware_service}"


class TestWorkerPathWithoutJwt:
    @pytest.mark.asyncio
    async def test_two_concurrent_processes_never_mix_up_reports_or_broker_urls(self):
        from auditor.application.use_cases.run_audit import RunAuditUseCase
        from auditor.domain.services.structural_validator import StructuralValidator
        from auditor.infrastructure.context_broker.ngsi_v2_mapper import NgsiV2Mapper

        class _FakeSchemaCatalog:
            async def resolve_data_model(self, entity_type):
                return None

            async def fetch_schema(self, data_model):
                raise AssertionError("nao deveria ser chamado sem data_model")

        class _FakeAuditRepository:
            def __init__(self):
                self.runs: dict = {}

            async def create_run(self, run) -> None:
                self.runs[run.id] = run

            async def append_report(self, run_id, tenant, report) -> None:
                self.runs[run_id].add_report(report)

            async def update_run_status(
                self, run_id, tenant, status, finished_at=None, failure_reason=None
            ) -> None:
                run = self.runs[run_id]
                run.status = status
                run.finished_at = finished_at
                run.failure_reason = failure_reason

            async def set_total_entities(self, run_id, tenant, total: int) -> None:
                self.runs[run_id].total_entities_discovered = total

            async def get_by_id(self, run_id, tenant):
                return self.runs.get(run_id)

        class _FakeUnitOfWork:
            def __init__(self, repository):
                self.audits = repository

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return None

        tenant_a = Tenant(fiware_service="worker_a", fiware_service_path="/")
        tenant_b = Tenant(fiware_service="worker_b", fiware_service_path="/")
        accounts = {
            tenant_a: _account(tenant_a, "https://orion-worker-a.example.com", "k-a"),
            tenant_b: _account(tenant_b, "https://orion-worker-b.example.com", "k-b"),
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(random.random() / 1000)
            fiware_service = request.headers.get("fiware-service")
            return httpx.Response(
                200,
                json=[
                    {"id": f"{fiware_service}:1", "type": "Streetlight"},
                    {"id": f"{fiware_service}:2", "type": "Streetlight"},
                ],
            )

        broker = TenantRoutedContextBroker(
            _FakeTenantAccountRepository(accounts, delay=True),
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        repository = _FakeAuditRepository()
        uow = _FakeUnitOfWork(repository)
        use_case = RunAuditUseCase(
            context_broker=broker,
            schema_catalog=_FakeSchemaCatalog(),
            validator=StructuralValidator(),
            mapper=NgsiV2Mapper(),
            uow=uow,
        )

        run_a = await use_case.create_run(tenant_a, EntityType("Streetlight"))
        run_b = await use_case.create_run(tenant_b, EntityType("Streetlight"))

        await asyncio.gather(
            use_case.process(run_a.id, tenant_a, EntityType("Streetlight")),
            use_case.process(run_b.id, tenant_b, EntityType("Streetlight")),
        )

        persisted_a = repository.runs[run_a.id]
        persisted_b = repository.runs[run_b.id]
        assert persisted_a.broker_url == "https://orion-worker-a.example.com"
        assert persisted_b.broker_url == "https://orion-worker-b.example.com"
        assert {r.entity_id for r in persisted_a.reports} == {"worker_a:1", "worker_a:2"}
        assert {r.entity_id for r in persisted_b.reports} == {"worker_b:1", "worker_b:2"}
