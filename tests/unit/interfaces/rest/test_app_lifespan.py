"""Fase 5 — wiring do AuditWorker no lifespan da API. Ver
.cursor/specs/fase5.spec.md, secao 3.

httpx.ASGITransport (usado nos demais testes de router) nao dispara o
lifespan do FastAPI por padrao — por isso este teste usa
starlette.testclient.TestClient, que dispara startup/shutdown de verdade,
so' para confirmar que create_app() sobe o AuditWorker como uma task em
background e cancela ela de forma limpa no shutdown (sem task orfa).
AuditWorker em si (consumo de fila/ack/nack) ja' e' testado isoladamente em
tests/unit/interfaces/worker/test_audit_worker.py — aqui o unico objetivo e'
a fiacao (wiring), por isso AuditWorker e' substituido por um fake.

O mesmo vale para CatalogSyncScheduler (follow-up pos-Fase 8, ver
interfaces/worker/catalog_sync_scheduler.py e seu proprio teste isolado em
test_catalog_sync_scheduler.py): sem substitui-lo por um fake aqui, o
lifespan de verdade chamaria get_sync_catalog_use_case() -> Postgres real,
que nao existe neste teste.
"""

from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

import auditor.interfaces.rest.app as app_module


class _FakeWorker:
    instances: list["_FakeWorker"] = []

    def __init__(self, queue, run_audit):
        self.queue = queue
        self.run_audit = run_audit
        self.run_forever_started = False
        self.cancelled = False
        _FakeWorker.instances.append(self)

    async def run_forever(self) -> None:
        self.run_forever_started = True
        try:
            await asyncio.Event().wait()  # nunca completa sozinho — so' cancelado no shutdown
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _FakeCatalogSyncScheduler:
    instances: list["_FakeCatalogSyncScheduler"] = []

    def __init__(self, sync_use_case, interval_seconds):
        self.sync_use_case = sync_use_case
        self.interval_seconds = interval_seconds
        self.run_forever_started = False
        self.cancelled = False
        _FakeCatalogSyncScheduler.instances.append(self)

    async def run_forever(self) -> None:
        self.run_forever_started = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_lifespan_starts_worker_sharing_the_container_queue_and_cancels_it_on_shutdown(monkeypatch):
    _FakeWorker.instances.clear()
    _FakeCatalogSyncScheduler.instances.clear()
    sentinel_queue = object()
    sentinel_use_case = object()
    sentinel_sync_use_case = object()
    monkeypatch.setattr(app_module, "get_job_queue", lambda: sentinel_queue)
    monkeypatch.setattr(app_module, "get_run_audit_use_case", lambda: sentinel_use_case)
    monkeypatch.setattr(app_module, "get_sync_catalog_use_case", lambda: sentinel_sync_use_case)
    monkeypatch.setattr(app_module, "AuditWorker", _FakeWorker)
    monkeypatch.setattr(app_module, "CatalogSyncScheduler", _FakeCatalogSyncScheduler)

    app = app_module.create_app()
    with TestClient(app) as client:
        response = client.get("/health/live")
        assert response.status_code == 200

        assert len(_FakeWorker.instances) == 1
        worker = _FakeWorker.instances[0]
        # a MESMA instancia que o router usa para enfileirar (get_job_queue
        # e' @lru_cache no container de verdade) — aqui confirmamos que o
        # lifespan passa exatamente o que get_job_queue()/
        # get_run_audit_use_case() devolvem, sem reconstruir nada por
        # conta propria.
        assert worker.queue is sentinel_queue
        assert worker.run_audit is sentinel_use_case
        assert worker.run_forever_started is True

        assert len(_FakeCatalogSyncScheduler.instances) == 1
        scheduler = _FakeCatalogSyncScheduler.instances[0]
        assert scheduler.sync_use_case is sentinel_sync_use_case
        assert scheduler.interval_seconds == app_module.get_settings().catalog_sync_interval_seconds
        assert scheduler.run_forever_started is True

    assert worker.cancelled is True
    assert scheduler.cancelled is True
