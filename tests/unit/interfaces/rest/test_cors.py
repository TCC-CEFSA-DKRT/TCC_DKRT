"""Fase 8, secao 9 -- CORS liberado para o frontend Angular local. Ver
.cursor/specs/fase8.spec.md. Usa starlette.testclient.TestClient (dispara
o lifespan de verdade, mesmo padrao de test_app_lifespan.py) so' para
confirmar que um preflight OPTIONS de localhost:4200 recebe os headers de
CORS esperados -- sem isso, todo fetch do navegador falharia antes mesmo
de chegar a um router.

Mesma tecnica de test_app_lifespan.py (AuditWorker/get_job_queue
substituidos por fakes via monkeypatch): sem isso, o LocalJobQueue real
(@lru_cache no container) fica preso ao event loop do primeiro
TestClient e o segundo teste deste arquivo quebra com "Queue is bound to
a different event loop" -- nao e' um bug de CORS, e' so' o custo de usar
TestClient de verdade duas vezes no mesmo processo.
"""

from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

import auditor.interfaces.rest.app as app_module


class _FakeWorker:
    def __init__(self, queue, run_audit):
        pass

    async def run_forever(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise


class _FakeCatalogSyncScheduler:
    def __init__(self, sync_use_case, interval_seconds):
        pass

    async def run_forever(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise


def _make_app(monkeypatch):
    monkeypatch.setattr(app_module, "get_job_queue", lambda: object())
    monkeypatch.setattr(app_module, "get_run_audit_use_case", lambda: object())
    monkeypatch.setattr(app_module, "get_sync_catalog_use_case", lambda: object())
    monkeypatch.setattr(app_module, "AuditWorker", _FakeWorker)
    monkeypatch.setattr(app_module, "CatalogSyncScheduler", _FakeCatalogSyncScheduler)
    return app_module.create_app()


class TestCorsPreflight:
    def test_preflight_from_the_local_angular_dev_server_is_allowed(self, monkeypatch):
        app = _make_app(monkeypatch)
        with TestClient(app) as client:
            response = client.options(
                "/audits",
                headers={
                    "Origin": "http://localhost:4200",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Fiware-Service",
                },
            )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:4200"

    def test_an_unlisted_origin_is_not_granted_cors_access(self, monkeypatch):
        app = _make_app(monkeypatch)
        with TestClient(app) as client:
            response = client.options(
                "/audits",
                headers={
                    "Origin": "http://evil.example.com",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Fiware-Service",
                },
            )

        assert "access-control-allow-origin" not in response.headers

    def test_content_disposition_is_exposed_so_the_frontend_can_read_the_pdf_filename(
        self, monkeypatch
    ):
        # Issue #23: sem Access-Control-Expose-Headers o navegador esconde o
        # nome do arquivo do PDF exportado do codigo Angular.
        app = _make_app(monkeypatch)
        with TestClient(app) as client:
            response = client.get("/health", headers={"Origin": "http://localhost:4200"})

        assert "content-disposition" in response.headers["access-control-expose-headers"].lower()
