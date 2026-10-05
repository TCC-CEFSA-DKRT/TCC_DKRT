"""Handler Lambda do consumidor de dead-letters — ADR-0017. Substitui
`AuditWorker._consume_dead_letters()` (`interfaces/worker/audit_worker.py`,
Fase 5): em vez de um loop de polling na DLQ, esta funcao Lambda e' acionada
pelo event source mapping da PROPRIA fila de dead-letters (recurso ja'
provisionado por `modules/queue`, Fase 9 — nenhuma mudanca de
infraestrutura de fila em si, so' um consumidor novo). Cada mensagem que
chega aqui ja' excedeu o `maxReceiveCount` configurado na `RedrivePolicy`
da fila principal — o mesmo significado de "chegou na DLQ" da Fase 5, so'
que entregue por invocacao em vez de `consume_dead_letters()`.

`mark_failed()` (RunAuditUseCase) e' deliberadamente o unico efeito aqui —
mesmo raciocinio de `AuditWorker._consume_dead_letters()`: garante que o
AuditRun correspondente vira FAILED com motivo visivel ao usuario
(`MAX_RETRIES_EXCEEDED_REASON`), nunca fica "pendente para sempre" sem
explicacao. Falha ao marcar (banco indisponivel, etc.) tambem reporta
`batchItemFailures` — mesmo mecanismo de reentrega parcial do
`worker_handler.py` — para nao perder silenciosamente o sinal de "run
falhou de vez" se a escrita no banco falhar."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from auditor.interfaces.aws_lambda._bootstrap import bootstrap_settings_from_aws

bootstrap_settings_from_aws()

from auditor.infrastructure.config.container import get_run_audit_use_case  # noqa: E402
from auditor.infrastructure.queue.sqs_job_queue import parse_audit_job  # noqa: E402
from auditor.interfaces.worker.audit_worker import MAX_RETRIES_EXCEEDED_REASON  # noqa: E402

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    return asyncio.run(_handle_async(event))


async def _handle_async(event: dict[str, Any]) -> dict[str, Any]:
    use_case = get_run_audit_use_case()
    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        job = parse_audit_job(record["body"])
        try:
            await use_case.mark_failed(job.run_id, job.tenant, reason=MAX_RETRIES_EXCEEDED_REASON)
        except Exception:
            logger.exception(
                "Falha ao marcar AuditRun run_id=%s como FAILED apos DLQ "
                "(messageId=%s) — reportando batchItemFailure para tentar de novo.",
                job.run_id,
                record.get("messageId"),
            )
            batch_item_failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": batch_item_failures}
