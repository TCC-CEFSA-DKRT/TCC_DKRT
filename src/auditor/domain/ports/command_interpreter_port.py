"""CommandInterpreterPort — ver .cursor/specs/fase8.spec.md, secao 0.3.

Traduz um comando em linguagem natural para os parametros de `POST
/audits` — nunca decide executar nada sozinho; so' interpreta. Distinto de
`SemanticAnalyzerPort` (Fase 7, analisa uma entidade ja' auditada):
aqui a entrada e' texto livre do usuario, nao uma entidade NGSI.

Issue #21 (console de linguagem natural) acrescentou duas intencoes:
- `"clarify"`: o pedido e' sobre auditoria, mas ambiguo demais para
  extrair parametros com seguranca — a tela faz uma pergunta de
  esclarecimento (`clarification_question`) em vez de oferecer confirmacao;
- `"out_of_scope"`: o pedido nao e' sobre entidades FIWARE — a tela explica
  isso e nada e' executado (nem uma consulta ao broker).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

CommandIntent = Literal["audit", "discovery", "clarify", "out_of_scope"]


@dataclass(frozen=True)
class AuditCommandInterpretation:
    entity_type: str | None
    entity_id: str | None
    confidence: float
    raw_command: str
    intent: CommandIntent = "audit"
    discovered_types: tuple[str, ...] | None = None
    broker_reachable: bool | None = None
    # Issue #21: pergunta mostrada ao usuario quando `intent == "clarify"`.
    clarification_question: str | None = None
    # Issue #21: `False` quando o interpretador (Ollama) nao respondeu
    # (rede/timeout/HTTP 5xx) — distingue "o servico esta fora" de "nao
    # entendi o comando", para a tela mostrar a mensagem certa.
    interpreter_available: bool = True


class CommandInterpreterPort(Protocol):
    async def interpret(self, command_text: str) -> AuditCommandInterpretation:
        """Nunca levanta excecao para fora — falha de rede, timeout ou saida
        que nao valida vira `AuditCommandInterpretation(entity_type=None,
        entity_id=None, confidence=0.0, raw_command=command_text)`: "nao
        entendi", nunca um tipo plausivel-mas-inventado. Falha de rede/HTTP
        marca tambem `interpreter_available=False`."""
        ...
