"""Diagnostico pontual (nao faz parte do projeto/testes) -- reproduz, passo
a passo e com timestamps, exatamente a mesma cadeia sincrona que
`interfaces/rest/app.py::_make_lifespan` executa ANTES do `yield` (ou seja,
antes do uvicorn poder imprimir "Application startup complete."). Objetivo:
achar qual chamada especifica esta' travando o startup da API sem precisar
adivinhar uma de cada vez.

Uso:
    python scripts/diagnose_startup.py

Se travar, a ULTIMA linha "iniciando: ..." impressa (sem o "OK" correspondente
depois) e' exatamente a chamada culpada -- Ctrl+C nesse ponto e me manda o
que apareceu.
"""

from __future__ import annotations

import sys
import time


def step(name, fn):
    print(f"[{time.strftime('%H:%M:%S')}] iniciando: {name}", flush=True)
    t0 = time.time()
    try:
        result = fn()
    except Exception as exc:  # queremos VER o erro, nao esconder
        print(f"[{time.strftime('%H:%M:%S')}] ERRO ({time.time() - t0:.2f}s) em {name}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        raise
    print(f"[{time.strftime('%H:%M:%S')}] OK ({time.time() - t0:.2f}s): {name}", flush=True)
    return result


def main() -> None:
    print(f"[{time.strftime('%H:%M:%S')}] Python: {sys.executable}", flush=True)

    step("import container", lambda: __import__(
        "auditor.infrastructure.config.container", fromlist=["container"]
    ))
    from auditor.infrastructure.config import container as c

    step("get_settings", c.get_settings)
    step("get_engine (sem conectar, so cria o objeto)", c.get_engine)
    step("get_http_client", c.get_http_client)
    step("import pysmartdatamodels (direto, isolado)", lambda: __import__(
        "pysmartdatamodels.pysmartdatamodels", fromlist=["pysmartdatamodels"]
    ))
    step("get_catalog_index (constroi CatalogIndex -- reimporta pysmartdatamodels)", c.get_catalog_index)
    step("get_catalog_sync_status_repository", c.get_catalog_sync_status_repository)
    step("get_schema_catalog", c.get_schema_catalog)
    step("get_context_broker", c.get_context_broker)
    step("get_unit_of_work", c.get_unit_of_work)
    step("get_embedder (so construtor -- modelo e' lazy, nao deve carregar peso aqui)", c.get_embedder)
    step("get_knowledge_retriever", c.get_knowledge_retriever)
    step("get_semantic_analyzer", c.get_semantic_analyzer)
    step("get_job_queue", c.get_job_queue)
    step("get_run_audit_use_case (cadeia completa, igual o lifespan faz)", c.get_run_audit_use_case)
    step("get_sync_catalog_use_case", c.get_sync_catalog_use_case)

    print(f"[{time.strftime('%H:%M:%S')}] TUDO OK -- nenhuma factory sincrona travou.", flush=True)


if __name__ == "__main__":
    main()
