import pytest

from context_broker_agent.services.slm_service import SLMService


@pytest.fixture
def heuristic_only(monkeypatch):
    """Garante que SLM caia na heurística mesmo se Ollama estiver rodando."""
    from context_broker_agent import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "slm_enabled", False)
    yield


@pytest.mark.parametrize(
    "text,expected_intent",
    [
        ("listar sensores", "query"),
        ("criar dispositivo Device:99", "provision"),
        ("avisar quando temperatura subir", "subscribe"),
    ],
)
def test_slm_heuristic_intents(heuristic_only, text, expected_intent):
    slm = SLMService()
    result = slm.interpret_query(text)
    assert result.intent == expected_intent
    assert result.source == "heuristic"


def test_extract_entity_id():
    assert SLMService._extract_entity_id("criar Sensor:abc-1") == "Sensor:abc-1"
