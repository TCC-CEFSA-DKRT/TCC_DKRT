"""Testes do entrypoint standalone do worker (interfaces/worker/main.py) —
fecha o gap descrito no proprio docstring do modulo: `worker.sh.tftpl`
sempre referenciou `auditor.interfaces.worker.main`, que nunca existia
antes desta correcao (Fase 9/ADR-0018).

So' `_run_until_stopped()` e' exercitado diretamente — e' a parte que nao
depende de sinais reais do SO (registrar `signal.SIGTERM`/`SIGINT` so' faz
sentido num processo de verdade, nunca dentro do processo do pytest).
"""

from __future__ import annotations

import asyncio

import pytest

from auditor.interfaces.worker.main import _run_until_stopped


class _StubWorker:
    """Fica preso em `run_forever()` ate' ser cancelado -- mesmo formato de
    `AuditWorker.run_forever()` (que so' retorna via CancelledError, nunca
    sozinho)."""

    def __init__(self) -> None:
        self.run_forever_called = False
        self.cancelled = False

    async def run_forever(self) -> None:
        self.run_forever_called = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _ExplodingWorker:
    """run_forever() termina sozinho com um erro -- deve propagar, nunca
    ficar preso esperando `stop` para sempre nem ser engolido em
    silencio."""

    async def run_forever(self) -> None:
        raise RuntimeError("falha irrecuperavel no consumo da fila")


@pytest.mark.asyncio
async def test_run_until_stopped_works_even_when_stop_is_already_set():
    """Regressao: um `stop` ja' resolvido no momento da chamada nao pode
    impedir o worker de rodar seu primeiro passo antes do cancelamento
    (ver o comentario de `_run_until_stopped` sobre `asyncio.Event.wait()`
    nao ceder o loop quando ja' setado)."""
    stub = _StubWorker()
    stop = asyncio.Event()
    stop.set()

    await _run_until_stopped(stub, stop)

    assert stub.run_forever_called
    assert stub.cancelled


@pytest.mark.asyncio
async def test_run_until_stopped_waits_for_the_stop_event_before_cancelling():
    stub = _StubWorker()
    stop = asyncio.Event()

    task = asyncio.create_task(_run_until_stopped(stub, stop))
    await asyncio.sleep(0.01)  # deixa run_forever() comecar antes de sinalizar parada
    assert stub.run_forever_called
    assert not stub.cancelled

    stop.set()
    await task

    assert stub.cancelled


@pytest.mark.asyncio
async def test_run_until_stopped_propagates_an_unexpected_worker_failure():
    stop = asyncio.Event()  # nunca setado -- so' a falha do worker deve terminar isto

    with pytest.raises(RuntimeError, match="falha irrecuperavel"):
        await _run_until_stopped(_ExplodingWorker(), stop)
