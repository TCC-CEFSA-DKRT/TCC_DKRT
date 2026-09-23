"""CommandInterpreterPort — ver .cursor/specs/fase8.spec.md, secao 0.3.

Traduz um comando em linguagem natural para os parametros de `POST
/audits` — nunca decide executar nada sozinho; so' interpreta. Distinto de
`SemanticAnalyzerPort` (Fase 7, analisa uma entidade ja' auditada):
aqui a entrada e' texto livre do usuario, nao uma entidade NGSI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuditCommandInterpretation:
    entity_type: str | None
    entity_id: str | None
    confidence: float
    raw_command: str


class CommandInterpreterPort(Protocol):
    async def interpret(self, command_text: str) -> AuditCommandInterpretation:
        """Nunca levanta excecao para fora — falha de rede, timeout ou saida
        que nao valida vira `AuditCommandInterpretation(entity_type=None,
        entity_id=None, confidence=0.0, raw_command=command_text)`: "nao
        entendi", nunca um tipo plausivel-mas-inventado."""
        ...
