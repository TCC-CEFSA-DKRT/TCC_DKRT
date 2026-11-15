"""Carga leve DENTRO do pytest (roda no CI sem subir servidor): 200 requisicoes
concorrentes contra a API in-process. Garante nenhuma falha sob concorrencia
e um teto de latencia generoso (evita flakiness em maquina lenta); a medicao
fina e' feita com Locust (locustfile.py)."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from .app_alvo import app

H = {"Fiware-Service": "openiot", "Fiware-ServicePath": "/"}
N = 200
P95_MAX_S = 2.0  # teto de CI; o criterio de aceitacao real (500 ms) e' medido no Locust

pytestmark = pytest.mark.req("RNF-01")


async def _uma(c: httpx.AsyncClient, i: int) -> tuple[int, float]:
    t0 = time.perf_counter()
    if i % 2:
        r = await c.get("/audits?page=1&page_size=20", headers=H)
    else:
        r = await c.post("/audits", json={"entity_type": "Streetlight"}, headers=H)
    return r.status_code, time.perf_counter() - t0


@pytest.mark.asyncio
async def test_ct_car_01_200_requisicoes_concorrentes_sem_erro_e_p95_sob_o_teto():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resultados = await asyncio.gather(*(_uma(c, i) for i in range(N)))

    codigos = [s for s, _ in resultados]
    tempos = sorted(t for _, t in resultados)
    assert all(s in (200, 202) for s in codigos), "houve resposta de erro sob concorrencia"
    assert tempos[int(0.95 * N) - 1] < P95_MAX_S
