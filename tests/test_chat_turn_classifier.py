import pytest

from context_broker_agent.models.intent import ChatTurnAnalysis
from context_broker_agent.utils.chat_turn_classifier import (
    apply_conversation_guard,
    requires_fiware_action,
    should_force_conversation,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("listar sensores do lab 64", True),
        ("Você consegue ver meus sensores no orion?", True),
        ("ele está indisponivel?", False),
        ("que saco", False),
        ("Ola", False),
    ],
)
def test_requires_fiware_action(text, expected):
    assert requires_fiware_action(text) is expected


def test_followup_after_orion_error_forces_conversation():
    ctx = [
        {"role": "user", "content": "ver sensores"},
        {
            "role": "assistant",
            "content": "Orion indisponível em localhost:1026. Execute: docker compose up -d",
        },
    ]
    analysis = ChatTurnAnalysis(
        response_type="fiware",
        assistant_message="Listando sensores.",
        operation="list",
        entity_type="Sensor",
        confidence=0.7,
        source="ollama",
    )
    assert should_force_conversation("ele está indisponivel?", analysis, ctx)

    fixed = apply_conversation_guard("ele está indisponivel?", analysis, ctx)
    assert fixed.response_type == "conversation"
    assert "localhost:1026" in fixed.assistant_message or "Orion" in fixed.assistant_message


def test_slm_guard_wrong_ollama_classification():
    from context_broker_agent.services.slm_service import SLMService

    slm = SLMService()
    ctx = [
        {"role": "assistant", "content": "Orion indisponível em localhost:1026."},
    ]
    wrong = ChatTurnAnalysis(
        response_type="fiware",
        assistant_message="Ação Orion list",
        operation="list",
        entity_type="Sensor",
        confidence=0.7,
        source="ollama",
    )
    fixed = apply_conversation_guard("que saco", wrong, ctx)
    assert fixed.response_type == "conversation"
    assert slm._analyze_chat_heuristic("que saco", None, None, ctx).response_type in (
        "conversation",
        "fiware",
    )


def test_capability_question_forces_conversation_even_with_high_confidence():
    """Quando o usuário pergunta sobre capacidades, não deve disparar Orion."""
    analysis = ChatTurnAnalysis(
        response_type="fiware",
        assistant_message=(
            "Desculpe, mas a persistência de dados é uma função complementar "
            "ao Context Broker. Use QuantumLeap ou STH-Comet."
        ),
        operation="query",
        entity_type="Sensor",
        confidence=0.9,
        source="ollama",
    )
    text = "Voce consegui persistir valores nos sensores do la64"
    assert should_force_conversation(text, analysis, [])

    fixed = apply_conversation_guard(text, analysis, [])
    assert fixed.response_type == "conversation"
    assert fixed.operation is None
    assert "persistência" in fixed.assistant_message


def test_meta_question_about_capability_with_verb_still_conversation():
    analysis = ChatTurnAnalysis(
        response_type="fiware",
        assistant_message="Poderemos consultar os sensores do Lab64 usando o Orion NGSI-v2.",
        operation="query",
        entity_type="Sensor",
        confidence=1.0,
        source="ollama",
    )
    text = "entendi, mas consulta dos sensores voce consegui?"
    assert should_force_conversation(text, analysis, [])
    fixed = apply_conversation_guard(text, analysis, [])
    assert fixed.response_type == "conversation"


def test_real_action_still_routed_to_fiware():
    analysis = ChatTurnAnalysis(
        response_type="fiware",
        assistant_message="Buscando dados no Context Broker Orion.",
        operation="list",
        entity_type="Sensor",
        confidence=0.9,
        source="ollama",
    )
    assert not should_force_conversation("liste os sensores do lab 64", analysis, [])
    assert not should_force_conversation("mostrar sensores", analysis, [])


def test_concrete_params_preserve_fiware():
    analysis = ChatTurnAnalysis(
        response_type="fiware",
        operation="query",
        entity_type="Sensor",
        ngsi_q="lab==64",
        confidence=0.85,
        source="ollama",
    )
    assert not should_force_conversation("sensores do lab 64", analysis, [])


def test_frustration_forces_conversation():
    ctx = [
        {"role": "assistant", "content": "Orion indisponível em localhost:1026."},
    ]
    analysis = ChatTurnAnalysis(
        response_type="fiware",
        operation="list",
        entity_type="Sensor",
        confidence=0.7,
        source="ollama",
    )
    fixed = apply_conversation_guard("que saco", analysis, ctx)
    assert fixed.response_type == "conversation"
    assert fixed.operation is None
