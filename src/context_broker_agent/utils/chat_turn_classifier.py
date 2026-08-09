"""Regras para separar conversa natural de ações FIWARE no modo chat."""

from __future__ import annotations

import re

from context_broker_multiagent.models.intent import ChatTurnAnalysis

FIWARE_ACTION_VERBS = (
    "listar",
    "lista",
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
    """Perguntas sobre status/erro OU capacidade do agente — sem pedido direto de dados."""
    lower = text.lower().strip()
    status_patterns = (
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
    capability_patterns = (
        r"\bvoc[eê]\s+(consegue|consegui|sabe|pode|poderia|faz|tem como|saberia)\b",
        r"\b(consegue|consegui|sabe|pode|poderia|saberia)\s+(persistir|guardar|salvar|gravar|armazenar|consultar|listar|criar|atualizar|apagar|fazer|buscar|mostrar|ajudar)\b",
        r"\b(consigo|posso|sabemos|podemos)\s+(persistir|guardar|consultar|listar|criar|atualizar)\b",
        r"\bo que\s+voc[eê]\s+(faz|sabe|pode)\b",
        r"\b(quem|o que)\s+(é\s+)?voc[eê]\b",
        r"\bcomo\s+(funciona|voc[eê]\s+funciona)\b",
        r"\b(entendi|certo|ok|legal)[\s,.!?]",
    )
    return any(re.search(p, lower) for p in (*status_patterns, *capability_patterns))


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


def _has_concrete_fiware_params(analysis: ChatTurnAnalysis) -> bool:
    """SLM extraiu parâmetros específicos o suficiente para justificar uma ação."""
    return bool(analysis.entity_id or analysis.ngsi_q or analysis.attribute)


def should_force_conversation(
    text: str,
    analysis: ChatTurnAnalysis,
    context_messages: list[dict[str, str]] | None,
) -> bool:
    """Evita chamar Orion quando o turno é reação, status, capacidade ou conversa.

    Princípio: só executa FIWARE quando há verbo de ação explícito OU parâmetros
    concretos extraídos (entity_id, ngsi_q, attribute). Sem isso, o SLM provavelmente
    confundiu uma pergunta conceitual com um pedido de dados.
    """
    if analysis.response_type != "fiware":
        return False

    ctx = context_messages or []
    lower = text.lower().strip()

    if is_frustration_only(text):
        return True

    # Perguntas de capacidade/status/meta SEMPRE são conversa, mesmo com verbo.
    # Ex.: "você consegue listar?" tem "listar" mas é pergunta, não comando.
    if is_meta_or_status_question(text):
        return True

    has_verb = requires_fiware_action(text)
    has_params = _has_concrete_fiware_params(analysis)

    # Sem verbo E sem parâmetros concretos → conversa (mesmo com confidence alta).
    if not has_verb and not has_params:
        return True

    if last_assistant_had_orion_error(ctx):
        if not has_verb and len(lower.split()) <= 10:
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


_GENERIC_FIWARE_MSG_PREFIXES = (
    "buscando",
    "consultando",
    "listando",
    "atualizando",
    "criando",
    "removendo",
    "deletando",
    "executando",
)


def _slm_message_looks_conversational(message: str) -> bool:
    """O SLM gerou texto rico (explicação real) e não confirmação de ação."""
    if not message:
        return False
    stripped = message.strip()
    if len(stripped) < 30:
        return False
    return not stripped.lower().startswith(_GENERIC_FIWARE_MSG_PREFIXES)


def apply_conversation_guard(
    text: str,
    analysis: ChatTurnAnalysis,
    context_messages: list[dict[str, str]] | None,
) -> ChatTurnAnalysis:
    """Reclassifica fiware → conversation quando as regras indicam.

    Preserva o assistant_message original do SLM se for uma resposta rica
    (explicação real); caso contrário usa um template contextual.
    """
    if not should_force_conversation(text, analysis, context_messages):
        return analysis

    if _slm_message_looks_conversational(analysis.assistant_message):
        reply = analysis.assistant_message.strip()
    else:
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
