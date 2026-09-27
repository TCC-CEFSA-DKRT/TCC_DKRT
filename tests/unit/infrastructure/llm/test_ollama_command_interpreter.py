"""Fase 8, secao 0.3 -- OllamaCommandInterpreter. Ver .cursor/specs/fase8.spec.md.

Mesmo padrao de tests/unit/infrastructure/llm/test_ollama_analyzer.py (Fase
7): httpx.MockTransport, sem rede real, sem Ollama de verdade.
"""

from __future__ import annotations

import json

import httpx
import pytest

from auditor.infrastructure.llm.ollama_command_interpreter import OllamaCommandInterpreter


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestPlausibleCommand:
    @pytest.mark.asyncio
    async def test_a_plausible_command_yields_a_plausible_ngsi_entity_type_and_high_confidence(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {"entity_type": "AirQualityObserved", "entity_id": None, "confidence": 0.92}
                    )
                },
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os sensores de qualidade do ar")

        assert result.entity_type == "AirQualityObserved"
        assert result.confidence == 0.92
        assert result.raw_command == "audite os sensores de qualidade do ar"

    @pytest.mark.asyncio
    async def test_prompt_sent_to_ollama_contains_the_raw_command_text(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200, json={"response": json.dumps({"entity_type": None, "confidence": 0.0})}
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        await interpreter.interpret("audite os postes de luz")

        assert "audite os postes de luz" in captured["body"]["prompt"]


class TestAmbiguousCommand:
    @pytest.mark.asyncio
    async def test_a_command_with_no_identifiable_entity_type_yields_none_and_low_confidence(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {"entity_type": None, "entity_id": None, "confidence": 0.2}
                    )
                },
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("faz uma coisa ai")

        assert result.entity_type is None
        assert result.confidence < 0.5


class TestNetworkFailure:
    @pytest.mark.asyncio
    async def test_connection_error_falls_back_to_no_interpretation_without_raising(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.entity_type is None
        assert result.entity_id is None
        assert result.confidence == 0.0
        assert result.raw_command == "audite os postes"

    @pytest.mark.asyncio
    async def test_http_500_falls_back_without_raising(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.confidence == 0.0


class TestMalformedOutput:
    @pytest.mark.asyncio
    async def test_non_json_response_falls_back_without_raising(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"response": "isso nao e' JSON valido"})

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.entity_type is None
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_out_of_range_confidence_is_clamped_not_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {"entity_type": "Streetlight", "entity_id": None, "confidence": 1.5}
                    )
                },
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.confidence == 1.0
