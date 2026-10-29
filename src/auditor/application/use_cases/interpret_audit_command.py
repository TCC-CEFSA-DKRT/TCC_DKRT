"""InterpretAuditCommandUseCase — ver .cursor/specs/fase8.spec.md, secao 0.3.

So' interpreta; NUNCA chama RunAuditUseCase.start() nem qualquer outra
acao — quem decide confirmar e disparar a auditoria de verdade e' a
interacao do usuario na tela "Natural Language" (Fase 8, secao 6), nunca o
backend sozinho. `tenant` e' recebido para manter o mesmo formato de
autorizacao/observabilidade dos demais use cases (Fase 4/5).

Issue #21 — regras aplicadas sobre o resultado do interpretador:
- interpretador indisponivel -> devolve como veio (a tela mostra "servico
  indisponivel", nunca um erro tecnico);
- `out_of_scope` -> devolve sem parametros e SEM consultar o broker (pedido
  fora do dominio FIWARE nao executa nada, nem leitura);
- `audit` sem tipo ou com confianca < MIN_CONFIDENCE_TO_CONFIRM -> vira
  `clarify` (pedido ambiguo nunca chega a tela como "pronto para confirmar");
- `clarify` -> lista os tipos do broker (best-effort) como sugestoes de
  resposta para a pergunta de esclarecimento;
- `discovery` -> lista os tipos do broker (comportamento original).
"""

from __future__ import annotations

from dataclasses import replace

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.ports.command_interpreter_port import (
    AuditCommandInterpretation,
    CommandInterpreterPort,
)
from auditor.domain.ports.context_broker_port import ContextBrokerPort
from auditor.domain.value_objects.tenant import Tenant

# Mesmo limiar documentado no prompt (command_interpretation.md) e usado
# pela tela (natural-language.component.ts): abaixo disso o comando e'
# considerado ambiguo.
MIN_CONFIDENCE_TO_CONFIRM = 0.5

DEFAULT_CLARIFICATION_QUESTION = (
    "Não ficou claro qual tipo de entidade você quer auditar. "
    "Qual destes tipos você quer auditar?"
)


class InterpretAuditCommandUseCase:
    def __init__(self, interpreter: CommandInterpreterPort, context_broker: ContextBrokerPort) -> None:
        self._interpreter = interpreter
        self._context_broker = context_broker

    async def execute(self, tenant: Tenant, command_text: str) -> AuditCommandInterpretation:
        interpretation = await self._interpreter.interpret(command_text)

        if not interpretation.interpreter_available:
            return interpretation

        if interpretation.intent == "out_of_scope":
            return replace(interpretation, entity_type=None, entity_id=None)

        if interpretation.intent == "audit" and _is_ambiguous(interpretation):
            interpretation = replace(
                interpretation,
                intent="clarify",
                entity_type=None,
                entity_id=None,
            )

        if interpretation.intent == "clarify":
            question = interpretation.clarification_question or DEFAULT_CLARIFICATION_QUESTION
            interpretation = replace(interpretation, clarification_question=question)
            return await self._with_broker_types(tenant, interpretation)

        if interpretation.intent == "discovery":
            return await self._with_broker_types(tenant, interpretation)

        return interpretation

    async def _with_broker_types(
        self, tenant: Tenant, interpretation: AuditCommandInterpretation
    ) -> AuditCommandInterpretation:
        try:
            types = await self._context_broker.list_entity_types(tenant)
        except ContextBrokerUnavailableError:
            return replace(interpretation, discovered_types=(), broker_reachable=False)
        return replace(interpretation, discovered_types=tuple(types), broker_reachable=True)


def _is_ambiguous(interpretation: AuditCommandInterpretation) -> bool:
    return (
        interpretation.entity_type is None
        or interpretation.confidence < MIN_CONFIDENCE_TO_CONFIRM
    )
