"""Fase 7 — OllamaAnalyzer. Ver .cursor/specs/fase7.spec.md, secao 5.1.

Usa httpx.MockTransport — sem rede real, sem Ollama de verdade (mesmo
padrao de tests/unit/infrastructure/context_broker/test_orion_adapter.py,
Fase 4). O teste golden contra o Qwen2.5 real via Ollama fica em
tests/golden/test_semantic_analyzer_golden.py.
"""

from __future__ import annotations

import json

import httpx
import pytest

from auditor.domain.entities.entity_report import InferenceBackend
from auditor.domain.entities.violation import (
    DetectionSource,
    Violation,
    ViolationSeverity,
)
from auditor.domain.ports.knowledge_retriever_port import (
    KnowledgeCategory,
    RetrievedChunk,
)
from auditor.domain.ports.semantic_analyzer_port import SemanticAnalysisContext
from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.llm.ollama_analyzer import OllamaAnalyzer

_ENTITY_TYPE = EntityType("Streetlight")

_STRUCTURAL_VIOLATION = Violation(
    attribute_path="temperature",
    severity=ViolationSeverity.ERROR,
    rule="required_property_missing",
    expected="temperature",
    found=None,
    message="Propriedade obrigatoria 'temperature' ausente.",
    detected_by=DetectionSource.STRUCTURAL,
)

_SYNONYM_CHUNK = RetrievedChunk(
    chunk_id="synonym-temperature",
    category=KnowledgeCategory.SYNONYM_GLOSSARY,
    content="O atributo canonico e' 'temperature'. Tambem visto como: temp, tempC, temperatura.",
    similarity=0.95,
    tags=(),
)


def _ctx(**overrides) -> SemanticAnalysisContext:
    defaults = dict(
        entity_id="urn:ngsi-ld:Streetlight:001",
        entity_type=_ENTITY_TYPE,
        plain_values={"id": "urn:ngsi-ld:Streetlight:001", "type": "Streetlight", "temp": 21.5},
        schema={"required": ["temperature"], "properties": {"temperature": {"type": "number"}}},
        structural_violations=(_STRUCTURAL_VIOLATION,),
        knowledge_chunks=(_SYNONYM_CHUNK,),
    )
    defaults.update(overrides)
    return SemanticAnalysisContext(**defaults)


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestPromptContent:
    @pytest.mark.asyncio
    async def test_request_body_contains_entity_attribute_and_synonym_chunk(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200, json={"response": json.dumps({"findings": [], "recommendations": []})}
            )

        analyzer = OllamaAnalyzer(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        await analyzer.analyze(_ctx())

        prompt = captured["body"]["prompt"]
        assert "temperature" in prompt
        assert "temp, tempC, temperatura" in prompt


class TestValidResponse:
    @pytest.mark.asyncio
    async def test_http_200_valid_json_is_parsed_per_section_2(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {
                            "findings": [],
                            "recommendations": [
                                {
                                    "attribute_path": "temp",
                                    "action": "rename_attribute",
                                    "proposed_patch": {"from": "temp", "to": "temperature"},
                                    "rationale": "sinonimo conhecido",
                                    "confidence": 0.9,
                                }
                            ],
                        }
                    )
                },
            )

        analyzer = OllamaAnalyzer(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await analyzer.analyze(_ctx())

        assert result.analysis_unavailable is False
        assert result.recommendations[0].action.value == "rename_attribute"


class TestInferenceUsage:
    """Fase 10 (.cursor/specs/fase10.spec.md, secao 3.4)."""

    @pytest.mark.asyncio
    async def test_total_duration_becomes_compute_seconds(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": json.dumps({"findings": [], "recommendations": []}),
                    "total_duration": 2_500_000_000,
                },
            )

        analyzer = OllamaAnalyzer(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await analyzer.analyze(_ctx())

        assert result.usage is not None
        assert result.usage.backend == InferenceBackend.OLLAMA
        assert result.usage.compute_seconds == pytest.approx(2.5)
        assert result.usage.prompt_tokens is None

    @pytest.mark.asyncio
    async def test_missing_total_duration_yields_none_compute_seconds(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"response": json.dumps({"findings": [], "recommendations": []})}
            )

        analyzer = OllamaAnalyzer(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await analyzer.analyze(_ctx())

        assert result.usage is not None
        assert result.usage.compute_seconds is None


class TestNetworkFailure:
    @pytest.mark.asyncio
    async def test_connection_error_yields_analysis_unavailable_without_raising(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        analyzer = OllamaAnalyzer(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await analyzer.analyze(_ctx())

        assert result.analysis_unavailable is True
        assert result.violations == ()
        # Falha de infraestrutura acontece antes de qualquer chamada
        # responder — nao ha tempo de computo pra registrar.
        assert result.usage is None

    @pytest.mark.asyncio
    async def test_timeout_yields_analysis_unavailable_without_raising(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        analyzer = OllamaAnalyzer(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await analyzer.analyze(_ctx())

        assert result.analysis_unavailable is True


class TestServerError:
    @pytest.mark.asyncio
    async def test_http_500_yields_analysis_unavailable_without_raising(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        analyzer = OllamaAnalyzer(
            client=_client_with_handler(handler), base_url="http://ollama:11434"
        )

        result = await analyzer.analyze(_ctx())

        assert result.analysis_unavailable is True
