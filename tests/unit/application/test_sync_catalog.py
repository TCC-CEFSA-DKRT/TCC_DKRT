"""Fase 8, secao 7 -- SyncCatalogUseCase.

Fakes de CatalogIndex e CatalogSyncStatusRepository -- confirma que
record() e' sempre chamado com o SyncResult (sucesso OU falha) e um
timestamp, nunca so' nos casos de sucesso (e' justamente a falha que a
tela "Catalog" precisa poder mostrar, ver CatalogSyncStatusRepository).

Tambem cobre a regressao real encontrada nesta sessao: `execute()` chamava
`CatalogIndex.sync()` (sincrono, bloqueante de rede) direto no event loop
— inofensivo enquanto so' o CLI `audit catalog sync` disparava isto, mas
travava o processo inteiro da API assim que CatalogSyncScheduler passou a
chamar isto automaticamente no mesmo event loop do servidor REST (ver o
comentario em sync_catalog.py). O teste
`test_execute_does_not_block_the_event_loop_while_sync_runs` prova que
outra coroutine concorrente continua progredindo durante um `sync()`
lento -- e' o que `asyncio.to_thread` garante e um `self._catalog_index.
sync()` direto NAO garantiria (ele congelaria o loop inteiro pela duracao
do `time.sleep`).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest

from auditor.application.use_cases.sync_catalog import SyncCatalogUseCase
from auditor.infrastructure.schema_catalog.catalog_index import SyncResult

_NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


class _FakeCatalogIndex:
    def __init__(self, result: SyncResult):
        self._result = result
        self.sync_called = False

    def sync(self) -> SyncResult:
        self.sync_called = True
        return self._result


class _SlowBlockingCatalogIndex:
    """Simula CatalogIndex.sync() de verdade: sincrono e bloqueante (usa
    `time.sleep`, nao `asyncio.sleep`) -- exatamente o tipo de chamada que
    `update_data()` faz de verdade contra a rede."""

    def __init__(self, result: SyncResult, *, delay_seconds: float) -> None:
        self._result = result
        self._delay_seconds = delay_seconds

    def sync(self) -> SyncResult:
        time.sleep(self._delay_seconds)
        return self._result


class _FakeStatusRepository:
    def __init__(self):
        self.recorded: list[tuple[SyncResult, datetime]] = []

    async def record(self, result: SyncResult, attempted_at: datetime) -> None:
        self.recorded.append((result, attempted_at))


class TestSyncCatalogUseCase:
    @pytest.mark.asyncio
    async def test_a_successful_sync_is_recorded_with_the_result_and_a_timestamp(self):
        result = SyncResult(success=True, models_count=42, reason=None)
        catalog_index = _FakeCatalogIndex(result)
        status_repository = _FakeStatusRepository()
        use_case = SyncCatalogUseCase(catalog_index, status_repository, clock=lambda: _NOW)

        returned = await use_case.execute()

        assert returned is result
        assert catalog_index.sync_called is True
        assert status_repository.recorded == [(result, _NOW)]

    @pytest.mark.asyncio
    async def test_a_failed_sync_is_also_recorded_never_silently_dropped(self):
        result = SyncResult(success=False, models_count=None, reason="Hugging Face Hub unreachable (403)")
        catalog_index = _FakeCatalogIndex(result)
        status_repository = _FakeStatusRepository()
        use_case = SyncCatalogUseCase(catalog_index, status_repository, clock=lambda: _NOW)

        returned = await use_case.execute()

        assert returned is result
        assert status_repository.recorded == [(result, _NOW)]

    @pytest.mark.asyncio
    async def test_execute_does_not_block_the_event_loop_while_sync_runs(self):
        """Regressao: sem `asyncio.to_thread`, um `CatalogIndex.sync()`
        lento e bloqueante (como o real, via `time.sleep`/rede) congelaria
        o event loop inteiro -- nenhuma outra coroutine progrediria
        durante a chamada. Isso e' exatamente o que travava a API inteira
        (CatalogSyncScheduler chamando isto na mesma thread/event loop do
        uvicorn logo no startup)."""
        result = SyncResult(success=True, models_count=10, reason=None)
        catalog_index = _SlowBlockingCatalogIndex(result, delay_seconds=0.2)
        status_repository = _FakeStatusRepository()
        use_case = SyncCatalogUseCase(catalog_index, status_repository, clock=lambda: _NOW)

        ticks = 0

        async def _tick_counter() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        counter_task = asyncio.create_task(_tick_counter())
        try:
            await use_case.execute()
        finally:
            counter_task.cancel()
            try:
                await counter_task
            except asyncio.CancelledError:
                pass

        # 0.2s de sync() lento / 0.02s por tick -> pelo menos alguns ticks
        # deveriam ter progredido SE o event loop nao tivesse sido
        # bloqueado. Um valor baixo mas positivo evita flakiness de timing
        # sem deixar passar uma regressao que zere `ticks` por completo.
        assert ticks >= 3, (
            f"so' {ticks} ticks progrediram durante o sync() lento -- "
            "isso indica que execute() esta bloqueando o event loop de novo "
            "(asyncio.to_thread removido ou quebrado)."
        )
