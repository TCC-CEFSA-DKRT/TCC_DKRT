"""Entrypoint standalone do AuditWorker — usado pelo systemd na instancia
EC2 do worker (ver infra/terraform/modules/compute/user_data/worker.sh.tftpl,
`ExecStart=.../python -m auditor.interfaces.worker.main`).

Gap real encontrado na Fase 9/ADR-0017 (registrado la' como "conhecido, nao
corrigido"): o `.tftpl` do worker sempre referenciou este modulo, mas ele
nunca foi escrito — aplicar `environments/homolog` (ex-`environments/academy`,
renomeado pela ADR-0018) provisionaria a infraestrutura com sucesso, mas o
servico `auditor-worker.service` cairia em loop de restart (`ExecStart`
apontando para um modulo inexistente), sem nenhum job sendo consumido da
fila SQS.

Diferente do Lambda (`interfaces/aws_lambda/worker_handler.py`, ADR-0017),
que e' invocado por lote via SQS event source mapping (sem processo de
longa duracao), este processo faz long-polling continuo via
`AuditWorker.run_forever()` (mesmo contrato da Fase 5 usado em
desenvolvimento com `LocalJobQueue` — aqui `container.get_job_queue()`
resolve para `SqsJobQueue` porque o `user_data` do EC2 ja' escreve
`QUEUE_BACKEND=sqs`/`SQS_QUEUE_URL` no `.env` da instancia, lido por
`Settings` via variavel de ambiente, sem nenhum bootstrap adicional).

Encerramento gracioso: `systemctl stop auditor-worker.service` manda
SIGTERM. Sem tratamento, o processo seria simplesmente morto pelo SO — o
que e' seguro aqui (nao ha' transacao aberta entre o `await` de um job e o
proximo: cada `process()`/`ack()`/`nack()` de `AuditWorker` e' atomico), mas
capturar o sinal deixa o log explicito sobre o motivo da saida em vez de um
traceback confuso, e cancela a task de `run_forever()` de forma limpa antes
do processo terminar.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from auditor.infrastructure.config.container import (
    get_job_queue,
    get_run_audit_use_case,
)
from auditor.interfaces.worker.audit_worker import AuditWorker

logger = logging.getLogger(__name__)


async def _run_until_stopped(worker: AuditWorker, stop: asyncio.Event) -> None:
    """Extraido de `_main()` para ser testavel sem depender de sinais reais
    do SO (que so' fazem sentido num processo de verdade, nunca num teste)
    — um teste so' precisa passar um `stop` (ja' resolvido ou nao) e um
    worker stub.

    Usa `asyncio.wait()` sobre as DUAS tasks (run_forever() e stop.wait()),
    em vez de criar a task de `run_forever()` e so' depois dar `await
    stop.wait()` direto: `asyncio.Event.wait()` retorna sem nunca ceder o
    loop quando o evento ja' esta' setado (`if self._value: return True`),
    entao um `stop` ja' resolvido no momento da chamada cancelaria
    `run_task` antes dele rodar seu primeiro passo — o worker nunca chegaria
    a executar nada. Envolver `stop.wait()` na sua propria task (e esperar
    as duas via `asyncio.wait`) garante que o loop sempre cede pelo menos
    uma vez, dando a `run_task` a chance de comecar antes de qualquer
    cancelamento."""
    run_task = asyncio.create_task(worker.run_forever())
    stop_task = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait({run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        if run_task in done and not run_task.cancelled():
            # run_forever() nao deveria terminar sozinho -- so' via
            # cancelamento daqui embaixo. Se terminou (ou levantou),
            # propaga em vez de mascarar um erro real como "parada normal".
            run_task.result()
    finally:
        for task in (run_task, stop_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(run_task, stop_task, return_exceptions=True)


async def _main() -> None:
    worker = AuditWorker(queue=get_job_queue(), run_audit=get_run_audit_use_case())
    stop = asyncio.Event()

    def _handle_signal(sig_name: str) -> None:
        logger.info("Sinal %s recebido — encerrando o worker.", sig_name)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig.name)

    logger.info("Auditor Worker pronto — consumindo jobs via JobQueuePort.")
    await _run_until_stopped(worker, stop)
    logger.info("Auditor Worker encerrado.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_main())


if __name__ == "__main__":
    main()
