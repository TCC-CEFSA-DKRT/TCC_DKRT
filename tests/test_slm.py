import pytest

from context_broker_multiagent.services.slm_service import SLMService


@pytest.mark.parametrize(
    "text,expected_intent",
    [
        ("listar sensores", "query"),
        ("criar dispositivo Device:99", "provision"),
        ("avisar quando temperatura subir", "subscribe"),
    ],
)
def test_slm_heuristic_intents(text, expected_intent):
    slm = SLMService()
    result = slm.interpret_query(text)
    assert result.intent == expected_intent
    assert result.source == "heuristic"
