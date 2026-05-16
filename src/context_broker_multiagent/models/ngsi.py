"""Modelos NGSI-v2 e interpretação SLM."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ENTITY_ID_PATTERN = re.compile(r"^[A-Za-z][\w-]*:[\w.-]+$")


class NgsiQueryParams(BaseModel):
    """Parâmetros de consulta NGSI-v2."""

    type: str | None = None
    id: str | None = None
    limit: int = Field(default=20, ge=1, le=1000)
    q: str | None = None
    attrs: str | None = None


class NgsiEntity(BaseModel):
    """Entidade NGSI-v2 simplificada."""

    id: str
    type: str
    attrs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        if not ENTITY_ID_PATTERN.match(value):
            msg = "entity_id deve seguir o formato Tipo:id (ex.: Sensor:001)"
            raise ValueError(msg)
        return value


class SlmInterpretation(BaseModel):
    """Saída da interpretação de linguagem natural."""

    intent: Literal["query", "provision", "subscribe", "analyze", "route"]
    ngsi_query: NgsiQueryParams | None = None
    entity: NgsiEntity | None = None
    raw_interpretation: str = ""
    source: Literal["heuristic", "phi-2", "ollama"] = "heuristic"
