"""OllamaCommandInterpreter — implementa CommandInterpreterPort via Ollama.
Ver .cursor/specs/fase8.spec.md, secao 0.3.

Reaproveita o mesmo servidor Ollama e o mesmo padrao de chamada/tratamento
de falha do `OllamaAnalyzer` (Fase 7) — prompt e formato de saida
diferentes (aqui: interpretacao de comando, nao diagnostico de entidade),
por isso um adaptador proprio em vez de forcar o mesmo metodo `analyze()`.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from auditor.domain.ports.command_interpreter_port import (
    AuditCommandInterpretation,
    CommandInterpreterPort,
)

_PROMPT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "prompts" / "command_interpretation.md"
)
_TEMPERATURE = 0.1
_LOW_CONFIDENCE_FALLBACK = 0.0


class _InterpretationOutputSchema(BaseModel):
    entity_type: str | None = None
    entity_id: str | None = None
    confidence: float = _LOW_CONFIDENCE_FALLBACK


def _build_prompt(command_text: str) -> str:
    template = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("%%COMMAND_TEXT%%", command_text)


def _fallback(command_text: str) -> AuditCommandInterpretation:
    return AuditCommandInterpretation(
        entity_type=None,
        entity_id=None,
        confidence=_LOW_CONFIDENCE_FALLBACK,
        raw_command=command_text,
    )


class OllamaCommandInterpreter(CommandInterpreterPort):
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str = "qwen2.5:7b-instruct",
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def interpret(self, command_text: str) -> AuditCommandInterpretation:
        prompt = _build_prompt(command_text)
        try:
            response = await self._client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": _TEMPERATURE},
                },
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            # Mesmo contrato do OllamaAnalyzer (Fase 7): nunca propaga —
            # "nao entendi" e' um resultado valido desta porta, nao uma
            # falha do endpoint que a chama.
            return _fallback(command_text)

        body = response.json()
        raw_output = body.get("response", "")
        try:
            parsed = _InterpretationOutputSchema.model_validate_json(raw_output)
        except (ValidationError, ValueError):
            return _fallback(command_text)

        confidence = max(0.0, min(1.0, parsed.confidence))
        return AuditCommandInterpretation(
            entity_type=parsed.entity_type,
            entity_id=parsed.entity_id,
            confidence=confidence,
            raw_command=command_text,
        )
