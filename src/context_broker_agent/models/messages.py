"""Contratos de mensagens entre orquestrador e agentes."""

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class OrchestrationStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"


class AgentMessage(BaseModel):
    """Entrada de um agente."""

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))


class AgentResponse(BaseModel):
    """Saída de um agente."""

    agent_name: str
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: float = 0.0


class VerificationResult(BaseModel):
    """Resultado da verificação pós-execução (ADR-0002): compara o que foi
    pedido com o que o Orion realmente confirmou, após re-consulta."""

    ok: bool
    diff: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class OrchestrationResult(BaseModel):
    """Resultado agregado da orquestração."""

    status: OrchestrationStatus
    responses: list[AgentResponse]
    aggregated_data: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = ""