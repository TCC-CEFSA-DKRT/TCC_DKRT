"""GET /health/live e GET /health/ready. Ver .cursor/specs/fase4.spec.md,
secao 4.4.

`live` nunca verifica dependencia externa — so' confirma que o processo esta
de pe (usado por orquestradores para decidir se reinicia o container).
`ready` verifica o banco — usado para decidir se envia trafego a' instancia.
Sao perguntas diferentes de proposito.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from auditor.infrastructure.config.container import get_engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(engine: AsyncEngine = Depends(get_engine)) -> dict[str, str]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database unavailable: {exc}",
        ) from exc
    return {"status": "ok"}
