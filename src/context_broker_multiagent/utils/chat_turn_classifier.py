"""Regras para separar conversa natural de ações FIWARE no modo chat."""

from __future__ import annotations

import re

from context_broker_multiagent.models.intent import ChatTurnAnalysis

FIWARE_ACTION_VERBS = (
    "listar",
    "liste",
    "mostrar",
    "mostre",
    "exibir",
    "consultar",
    "consulte",
    "buscar",
    "busque",
    "obter",
    "traga",
    "criar",
    "crie",
    "cadastrar",
    "atualizar",
    "alterar",
    "apagar",
    "remover",
    "deletar",
    "excluir",
    "inserir",
    "provisionar",
    "quantos",
    "quantas",
    "deletar",
)

ORION_ERROR_HINTS = (
    "indisponível",
    "indisponivel",
    "offline",
    "não consegui acessar",
    "nao consegui acessar",
    "docker compose",
    "localhost:1026",
    "orion indispon",
)

FRUSTRATION_PHRASES = (
    "que saco",
    "que chato",
    "aff",
    "poxa",
    "droga",
    "nossa",
    "putz",
    "sacanagem",
    "não aguento",
    "nao aguento",
)


def requires_fiware_action(text: str) -> bool:
    """True quando o usuário pede uma operação explícita no Context Broker."""
    lower = text.lower()
    if any(v in lower for v in FIWARE_ACTION_VERBS):
        return True
    if re.search(
        r"\bver\s+(meus?|minhas?|os|as|o|a)?\s*(sensores|entidades|devices|dispositivos)\b",
        lower,
    ):
        return True
    if re.search(
        r"\b(quais|qual)\s+(s[aã]o|é)?\s*(os|as)?\s*(sensores|entidades|devices)\b",
        lower,
    ):
        return True
    if re.search(r"\b(me\s+)?(mostra|traz|busca)\b", lower):
        return True
    return False


def is_meta_or_status_question(text: str) -> bool:
    """Perguntas sobre disponibilidade/erro, sem pedido de dados NGSI."""
    lower = text.lower().strip()
    patterns = (
        r"\b(est[aá]|t[aá])\s+(indispon[ií]vel|offline|fora|down)\b",
        r"\bindispon[ií]vel\b",
        r"\b(por que|porque)\s+(n[aã]o|nao)\s+(funciona|conecta|abre)\b",
        r"\b(n[aã]o|nao)\s+(funciona|conecta)\b",
        r"\bfunciona\b",
        r"\bele\s+(est[aá]|e\s+est[aá])\b",
        r"\bisso\s+(est[aá]|significa|quer dizer)\b",
        r"\bo que\s+(significa|aconteceu|houve)\b",
        r"\best[aá]\s+offline\b",
        r"\bcaiu\b",
    )
    return any(re.search(p, lower) for p in patterns)


def is_frustration_only(text: str) -> bool:
    lower = text.lower().strip()
    if not any(p in lower for p in FRUSTRATION_PHRASES):
        return False
    return len(lower.split()) <= 6 and not requires_fiware_action(text)


def last_assistant_had_orion_error(context_messages: list[dict[str, str]]) -> bool:
    for msg in reversed(context_messages):
        if msg.get("role") != "assistant":
            continue
        body = msg.get("content", "").lower()
        return any(h in body for h in ORION_ERROR_HINTS)
    return False


def should_force_conversation(
    text: str,
    analysis: ChatTurnAnalysis,
    context_messages: list[dict[str, str]] | None,
) -> bool:
    """Evita chamar Orion quando o turno é reação, status ou follow-up ao erro."""
    if analysis.response_type != "fiware":
        return False

    ctx = context_messages or []
    lower = text.lower().strip()

    if is_frustration_only(text):
        return True

    if is_meta_or_status_question(text) and not requires_fiware_action(text):
        return True

    if last_assistant_had_orion_error(ctx):
        if is_meta_or_status_question(text) or is_frustration_only(text):
            return True
        if len(lower.split()) <= 10 and not requires_fiware_action(text):
            return True

    if not requires_fiware_action(text) and analysis.confidence < 0.88:
        return True

    return False


def contextual_conversation_reply(
    text: str,
    context_messages: list[dict[str, str]] | None,
) -> str:
    """Resposta natural quando o SLM classificou fiware por engano."""
    lower = text.lower().strip()
    had_error = last_assistant_had_orion_error(context_messages or [])

    if is_frustration_only(text):
        if had_error:
            return (
                "Entendo — é frustrante quando o Orion não responde. "
                "Nesta máquina ele costuma ficar offline até subir o Docker: "
                "docker compose up -d (e opcionalmente python scripts/seed_orion.py). "
                "Posso explicar o passo a passo ou ajudar com outra dúvida."
            )
        return (
            "Sei que é chato. Me diga o que você queria fazer "
            "(consultar sensores, criar entidade, etc.) que eu oriento."
        )

    if is_meta_or_status_question(text):
        if had_error:
            return (
                "Sim — na última tentativa o Orion em localhost:1026 não estava acessível. "
                "Isso é normal se o container não estiver rodando. "
                "Para testar de verdade: docker compose up -d"
            )
        return (
            "O Orion (FIWARE Context Broker) precisa estar rodando em localhost:1026. "
            "Use /status no terminal para ver Ollama e Orion, ou docker compose up -d para subir."
        )

    return (
        "Posso conversar ou consultar o Context Broker quando você pedir explicitamente "
        "(ex.: listar sensores do lab 64). O que você precisa?"
    )


def apply_conversation_guard(
    text: str,
    analysis: ChatTurnAnalysis,
    context_messages: list[dict[str, str]] | None,
) -> ChatTurnAnalysis:
    """Reclassifica fiware → conversation quando as regras indicam."""
    if not should_force_conversation(text, analysis, context_messages):
        return analysis

    reply = contextual_conversation_reply(text, context_messages)

    return ChatTurnAnalysis(
        response_type="conversation",
        assistant_message=reply,
        operation=None,
        entity_type=None,
        entity_id=None,
        attribute=None,
        ngsi_q=None,
        missing_fields=[],
        confidence=max(analysis.confidence, 0.85),
        source=analysis.source,
    )
