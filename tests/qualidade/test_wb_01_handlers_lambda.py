"""Caixa-branca: handlers Lambda de producao (RF-08, ADR-0017).

`worker_handler` e `worker_dlq_handler` rodam em producao (SQS -> Lambda) e
estavam com 0 % de cobertura. Teste de caminho basico (complexidade
ciclomatica V(G) = 3 em cada `_handle_async`: laco `for`, `try/except`):
  C1: evento sem Records            -> nenhum use case chamado, falhas = []
  C2: registro processado com exito -> use case chamado, falhas = []
  C3: use case levanta excecao      -> messageId em batchItemFailures
  C4: lote misto (ok, falha, ok)    -> so' o do meio reportado; o laco NAO
                                       para na falha (mensagens seguintes processadas)
O use case e' MOCK (AsyncMock): nada de banco, fila ou rede."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.interfaces.aws_lambda import worker_dlq_handler, worker_handler
from auditor.interfaces.worker.audit_worker import MAX_RETRIES_EXCEEDED_REASON

from .casos import Caso, param


def _registro(message_id: str, run_id: UUID | None = None, entity_type="Streetlight") -> dict:
    corpo = dict(
        run_id=str(run_id or uuid4()), fiware_service="openiot", fiware_service_path="/",
        entity_type=entity_type, entity_id=None, enqueued_at=datetime.now(timezone.utc).isoformat(),
    )
    return {"messageId": message_id, "body": json.dumps(corpo)}


# resultado de cada chamada ao use case: None = sucesso, Exception = falha
_PRE = "Use case substituído por AsyncMock; bootstrap AWS sem variáveis (no-op)."
CAMINHOS = [
    ("C1", "Evento sem Records", [], []),
    ("C2", "Um registro processado com êxito", [None], []),
    ("C3", "Um registro cujo processamento falha", [RuntimeError("boom")], ["m0"]),
    ("C4", "Lote misto (ok, falha, ok): laço continua após a falha", [None, RuntimeError("x"), None], ["m1"]),
]


def _casos(base: int, handler: str):
    saida = []
    for i, (cid, nome, efeitos, falhas) in enumerate(CAMINHOS, start=1):
        saida.append((
            Caso(f"CT-WB-{base + i:02d}", "RF-08", "CB", f"{handler}: caminho {cid} — {nome}",
                 f"Invocar _handle_async({handler}) com o evento SQS simulado.", _PRE,
                 f"{len(efeitos)} registro(s); efeitos={['ok' if e is None else 'erro' for e in efeitos]}",
                 f"batchItemFailures = {falhas}; use case chamado {len(efeitos)}x", "Alta"),
            efeitos, falhas))
    return saida


CASOS_WORKER = _casos(0, "worker_handler")
CASOS_DLQ = _casos(4, "worker_dlq_handler")


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,efeitos,falhas", [param(*t) for t in CASOS_WORKER])
async def test_worker_handler_caminhos(monkeypatch, caso, efeitos, falhas):
    uc = AsyncMock()
    uc.process.side_effect = efeitos
    monkeypatch.setattr(worker_handler, "get_run_audit_use_case", lambda: uc)
    registros = [_registro(f"m{i}") for i in range(len(efeitos))]

    r = await worker_handler._handle_async({"Records": registros})

    assert r == {"batchItemFailures": [{"itemIdentifier": m} for m in falhas]}
    assert uc.process.await_count == len(efeitos)


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,efeitos,falhas", [param(*t) for t in CASOS_DLQ])
async def test_worker_dlq_handler_caminhos(monkeypatch, caso, efeitos, falhas):
    uc = AsyncMock()
    uc.mark_failed.side_effect = efeitos
    monkeypatch.setattr(worker_dlq_handler, "get_run_audit_use_case", lambda: uc)
    registros = [_registro(f"m{i}") for i in range(len(efeitos))]

    r = await worker_dlq_handler._handle_async({"Records": registros})

    assert r == {"batchItemFailures": [{"itemIdentifier": m} for m in falhas]}
    assert uc.mark_failed.await_count == len(efeitos)


@pytest.mark.asyncio
@pytest.mark.req("RF-08")
async def test_ct_wb_09_worker_repassa_o_job_completo_ao_use_case(monkeypatch):
    uc = AsyncMock()
    monkeypatch.setattr(worker_handler, "get_run_audit_use_case", lambda: uc)
    run_id = uuid4()

    await worker_handler._handle_async({"Records": [_registro("m0", run_id)]})

    uc.process.assert_awaited_once_with(run_id, Tenant("openiot", "/"), EntityType("Streetlight"), None)


@pytest.mark.asyncio
@pytest.mark.req("RF-08")
async def test_ct_wb_10_dlq_marca_run_como_falho_com_o_motivo_padrao(monkeypatch):
    uc = AsyncMock()
    monkeypatch.setattr(worker_dlq_handler, "get_run_audit_use_case", lambda: uc)
    run_id = uuid4()

    await worker_dlq_handler._handle_async({"Records": [_registro("m0", run_id)]})

    uc.mark_failed.assert_awaited_once_with(run_id, Tenant("openiot", "/"), reason=MAX_RETRIES_EXCEEDED_REASON)


@pytest.mark.req("RF-08")
@pytest.mark.parametrize("modulo,metodo", [(worker_handler, "process"), (worker_dlq_handler, "mark_failed")], ids=["CT-WB-11-worker", "CT-WB-12-dlq"])
def test_handler_sincrono_executa_o_laco_de_eventos(monkeypatch, modulo, metodo):
    uc = AsyncMock()
    monkeypatch.setattr(modulo, "get_run_audit_use_case", lambda: uc)

    r = modulo.handler({"Records": [_registro("m0")]}, None)

    assert r == {"batchItemFailures": []}
    getattr(uc, metodo).assert_awaited_once()


_ALB_EVENT = {
    "httpMethod": "GET", "path": "/health/live", "queryStringParameters": {}, "body": None, "isBase64Encoded": False,
    "headers": {"host": "api.exemplo.com", "x-forwarded-for": "1.1.1.1", "x-forwarded-proto": "https", "x-forwarded-port": "443"},
    "requestContext": {"elb": {"targetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:1:targetgroup/api/1"}},
}


@pytest.mark.req("RF-08")
def test_ct_wb_21_api_handler_traduz_evento_do_alb_para_a_app_fastapi():
    from auditor.interfaces.aws_lambda import api_handler  # import tardio: cria a app (Mangum)

    r = api_handler.handler(_ALB_EVENT, None)

    assert r["statusCode"] == 200 and r["body"] == '{"status":"ok"}'


_PRE_C = _PRE
CASOS_EXTRA = [
    Caso("CT-WB-21", "RF-08", "CB", "API Lambda: evento do ALB chega à app FastAPI (Mangum)", "Chamar api_handler.handler(evento_ALB, None) com GET /health/live.", "Sem variáveis AWS (bootstrap no-op)", "evento ALB GET /health/live", "statusCode=200 e corpo {\"status\":\"ok\"}", "Alta"),
    Caso("CT-WB-09", "RF-08", "CB", "Worker repassa run_id/tenant/tipo/id ao use case", "Invocar _handle_async com 1 registro e verificar os argumentos.", _PRE_C, "registro com entity_type=Streetlight", "process(run_id, Tenant, EntityType, None)", "Alta"),
    Caso("CT-WB-10", "RF-08", "CB", "DLQ marca o run como FAILED com o motivo padrão", "Invocar _handle_async da DLQ com 1 registro.", _PRE_C, "registro da DLQ", f"mark_failed(run_id, tenant, reason=MAX_RETRIES_EXCEEDED_REASON)", "Alta"),
    Caso("CT-WB-11", "RF-08", "CB", "Entrada síncrona do worker (handler)", "Chamar handler(event, None) — usa asyncio.run.", _PRE_C, "1 registro", "{'batchItemFailures': []}"),
    Caso("CT-WB-12", "RF-08", "CB", "Entrada síncrona da DLQ (handler)", "Chamar handler(event, None) — usa asyncio.run.", _PRE_C, "1 registro", "{'batchItemFailures': []}"),
]
CASOS = [t[0] for t in CASOS_WORKER] + [t[0] for t in CASOS_DLQ] + CASOS_EXTRA
