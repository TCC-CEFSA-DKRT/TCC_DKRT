from unittest.mock import AsyncMock, patch

import pytest

from context_broker_agent.services.ollama_client import OllamaClient
from context_broker_agent.services.slm_service import SLMService


@pytest.mark.asyncio
async def test_check_ollama_lists_models():
    client = OllamaClient(base_url="http://test", model="qwen2.5")
    with patch.object(client, "list_models", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = ["qwen2.5:latest", "llama3"]
        slm = SLMService(ollama=client)
        with patch("context_broker_agent.services.slm_service.get_settings") as gs:
            gs.return_value.ollama_model = "qwen2.5"
            info = await slm.check_ollama()
    assert info["model_available"] is True


def test_interpret_ollama_parses_json():
    mock_client = OllamaClient(base_url="http://test", model="qwen2.5")
    mock_client.chat = AsyncMock(
        return_value='{"intent": "query", "ngsi_query": {"type": "Sensor", "limit": 10}, "entity": null}',
    )
    slm = SLMService(ollama=mock_client)
    with patch("context_broker_agent.services.slm_service.get_settings") as gs:
        gs.return_value.slm_enabled = True
        gs.return_value.slm_provider = "ollama"
        result = slm.interpret_query("listar sensores de temperatura")
    assert result.source == "ollama"
    assert result.intent == "query"
    assert result.ngsi_query is not None
    assert result.ngsi_query.type == "Sensor"
