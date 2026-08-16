"""Intent e análise de turno para o modo chat DKRT."""

from typing import Literal

from pydantic import BaseModel, Field

Operation = Literal["query", "create", "update", "list", "delete", "subscribe", "iot_provision"]
ResponseType = Literal["conversation", "fiware", "clarify"]


class ChatIntent(BaseModel):
    """Parâmetros NGSI quando a ação é no Orion."""

    operation: Operation = "query"
    entity_type: str | None = "Sensor"
    entity_id: str | None = None
    attribute: str | None = None
    ngsi_q: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_text: str = ""
    source: Literal["ollama", "llama_cpp", "heuristic"] = "heuristic"

    def summary(self) -> str:
        parts = [f"op={self.operation}", f"conf={self.confidence:.0%}"]
        if self.entity_type:
            parts.append(f"type={self.entity_type}")
        if self.entity_id:
            parts.append(f"id={self.entity_id}")
        if self.attribute:
            parts.append(f"attr={self.attribute}")
        if self.ngsi_q:
            parts.append(f"q={self.ngsi_q}")
        return " | ".join(parts)


class ChatTurnAnalysis(BaseModel):
    """Resultado da análise de um turno: conversa, FIWARE ou pedido de dados."""

    response_type: ResponseType = "conversation"
    assistant_message: str = ""
    operation: Operation | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    attribute: str | None = None
    ngsi_q: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: Literal["ollama", "llama_cpp", "heuristic"] = "heuristic"

    def to_fiware_intent(self, raw_text: str = "") -> ChatIntent:
        """Converte para ChatIntent quando response_type == fiware."""
        return ChatIntent(
            operation=self.operation or "query",
            entity_type=self.entity_type or "Sensor",
            entity_id=self.entity_id,
            attribute=self.attribute,
            ngsi_q=self.ngsi_q,
            confidence=self.confidence,
            raw_text=raw_text,
            source=self.source,
        )

    def needs_clarification(self) -> bool:
        if self.response_type == "clarify":
            return True
        if self.response_type != "fiware":
            return False
        op = self.operation or "query"
        if op in ("update", "delete") and not self.entity_id:
            return True
        if op == "create" and not self.entity_type:
            return True
        return bool(self.missing_fields)