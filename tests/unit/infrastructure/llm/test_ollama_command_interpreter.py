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


class TestIntentClassification:
    @pytest.mark.asyncio
    async def test_missing_intent_defaults_to_audit_and_keeps_extracted_type(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {"entity_type": "Streetlight", "entity_id": None, "confidence": 0.9}
                    )
                },
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.intent == "audit"
        assert result.entity_type == "Streetlight"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_discovery_intent_is_propagated_without_broker_data(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {
                            "intent": "discovery",
                            "entity_type": None,
                            "entity_id": None,
                            "confidence": 0.9,
                        }
                    )
                },
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("quais entidades existem?")

        assert result.intent == "discovery"
        assert result.confidence == 0.9
        assert result.discovered_types is None
        assert result.broker_reachable is None

    @pytest.mark.asyncio
    async def test_discovery_intent_discards_any_entity_type_or_id_the_model_returned(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {
                            "intent": "discovery",
                            "entity_type": "Streetlight",
                            "entity_id": "urn:x",
                            "confidence": 0.8,
                        }
                    )
                },
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("quais entidades existem?")

        assert result.entity_type is None
        assert result.entity_id is None
        assert result.intent == "discovery"

    @pytest.mark.asyncio
    async def test_unknown_intent_value_falls_back_to_no_interpretation(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {
                            "intent": "list_everything",
                            "entity_type": "Streetlight",
                            "confidence": 0.9,
                        }
                    )
                },
            )

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.intent == "audit"
        assert result.entity_type is None
        assert result.confidence == 0.0
        assert result.raw_command == "audite os postes"

    @pytest.mark.asyncio
    async def test_connection_error_fallback_is_audit_intent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.intent == "audit"

    @pytest.mark.asyncio
    async def test_prompt_teaches_the_discovery_intent(self):
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

        assert '"intent"' in captured["body"]["prompt"]
        assert "discovery" in captured["body"]["prompt"]


def _interpreter_returning(payload: dict) -> OllamaCommandInterpreter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": json.dumps(payload)})

    return OllamaCommandInterpreter(
        client=_client_with_handler(handler), base_url="http://ollama:11434"
    )


class TestClarifyAndOutOfScopeIntents:
    """Issue #21 -- console de linguagem natural."""

    @pytest.mark.asyncio
    async def test_clarify_intent_propagates_the_question_and_discards_any_guessed_type(self):
        interpreter = _interpreter_returning(
            {
                "intent": "clarify",
                "entity_type": "AirQualityObserved",
                "entity_id": None,
                "confidence": 0.4,
                "clarification_question": "  Quais sensores voce quer auditar?  ",
            }
        )

        result = await interpreter.interpret("audite os sensores")

        assert result.intent == "clarify"
        assert result.entity_type is None
        assert result.clarification_question == "Quais sensores voce quer auditar?"
        assert result.interpreter_available is True

    @pytest.mark.asyncio
    async def test_out_of_scope_intent_discards_type_and_id(self):
        interpreter = _interpreter_returning(
            {
                "intent": "out_of_scope",
                "entity_type": "Streetlight",
                "entity_id": "urn:x",
                "confidence": 0.95,
                "clarification_question": None,
            }
        )

        result = await interpreter.interpret("qual a capital da Franca?")

        assert result.intent == "out_of_scope"
        assert result.entity_type is None
        assert result.entity_id is None
        assert result.clarification_question is None

    @pytest.mark.asyncio
    async def test_question_is_ignored_when_the_intent_is_not_clarify(self):
        interpreter = _interpreter_returning(
            {
                "intent": "audit",
                "entity_type": "Streetlight",
                "entity_id": None,
                "confidence": 0.9,
                "clarification_question": "pergunta que nao deveria aparecer",
            }
        )

        result = await interpreter.interpret("audite os postes")

        assert result.clarification_question is None
        assert result.entity_type == "Streetlight"

    @pytest.mark.asyncio
    async def test_blank_entity_type_is_treated_as_null(self):
        interpreter = _interpreter_returning(
            {"intent": "audit", "entity_type": "   ", "entity_id": "", "confidence": 0.9}
        )

        result = await interpreter.interpret("audite")

        assert result.entity_type is None
        assert result.entity_id is None

    @pytest.mark.asyncio
    async def test_prompt_teaches_clarify_and_out_of_scope_intents(self):
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

        prompt = captured["body"]["prompt"]
        assert "clarify" in prompt
        assert "out_of_scope" in prompt
        assert "clarification_question" in prompt


class TestInterpreterAvailability:
    """Issue #21 -- distinguir "servico fora do ar" de "nao entendi"."""

    @pytest.mark.asyncio
    async def test_connection_error_marks_the_interpreter_as_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.interpreter_available is False

    @pytest.mark.asyncio
    async def test_timeout_marks_the_interpreter_as_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.interpreter_available is False
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_http_500_marks_the_interpreter_as_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.interpreter_available is False

    @pytest.mark.asyncio
    async def test_malformed_output_means_not_understood_but_service_available(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"response": "isso nao e' JSON valido"})

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.interpreter_available is True
        assert result.entity_type is None

    @pytest.mark.asyncio
    async def test_non_json_http_body_falls_back_without_raising(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>proxy error</html>")

        interpreter = OllamaCommandInterpreter(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await interpreter.interpret("audite os postes")

        assert result.entity_type is None
        assert result.confidence == 0.0
