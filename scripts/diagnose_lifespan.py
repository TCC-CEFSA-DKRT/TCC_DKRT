"""Diagnostico pontual (nao faz parte do projeto/testes) -- entra e sai do
`_lifespan` de verdade, dentro de um event loop real (diferente de
diagnose_startup.py, que so testou as factories sincronas fora de um loop).
Isola se o travamento esta' dentro do proprio `_make_lifespan` (o
`asyncio.create_task(...)` + `yield`) ou na camada do uvicorn/starlette por
cima dele.

Uso:
    python scripts/diagnose_lifespan.py
"""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI

from auditor.interfaces.rest.app import _make_lifespan


async def main() -> None:
    app = FastAPI()
    lifespan = _make_lifespan(start_background_workers=True)

    print(f"[{time.strftime('%H:%M:%S')}] entrando no lifespan (__aenter__)...", flush=True)
    t0 = time.time()
    async with lifespan(app):
        print(
            f"[{time.strftime('%H:%M:%S')}] ENTROU OK ({time.time() - t0:.2f}s) "
            "-- o lifespan em si nao trava.",
            flush=True,
        )
        await asyncio.sleep(1)
    print(f"[{time.strftime('%H:%M:%S')}] saiu do lifespan OK (__aexit__ tambem nao trava).", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
