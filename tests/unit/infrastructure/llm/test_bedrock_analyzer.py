"""Fase 7 — BedrockAnalyzer. Ver .cursor/specs/fase7.spec.md, secao 6:
escopo desta fase e' so' a FORMA (implementa SemanticAnalyzerPort, pode ser
escolhido pelo container) — sem teste de integracao contra AWS real.
Cliente Bedrock injetado como fake (Protocol estrutural, sem boto3 real).
"""

from __future__ import annotations

import json

import pytest

from auditor.domain.entities.entity_report import InferenceBackend
from auditor.domain.ports.knowledge_retriever_port import (
    KnowledgeCategory,
    RetrievedChunk,
)
from auditor.domain.ports.semantic_analyzer_port import SemanticAnalysisContext
from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.llm.bedrock_analyzer import BedrockAnalyzer


def _ctx() -> SemanticAnalysisContext:
    return SemanticAnalysisContext(
        entity_id="urn:1",
        entity_type=EntityType("Streetlight"),
        plain_values={"id": "urn:1", "type": "Streetlight", "temp": 21.5},
        schema={"required": ["temperature"]},
        structural_violations=(),
        knowledge_chunks=(
            RetrievedChunk(
                chunk_id="c1",
                category=KnowledgeCategory.CONVENTION,
                content="texto",
                similarity=0.5,
                tags=(),
            ),
        ),
    )


class _FakeBedrockBody:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw


class _FakeBedrockClient:
    def __init__(self, response_body: dict | None = None, error: Exception | None = None):
        self._response_body = response_body
        self._error = error
        self.calls: list[dict] = []

    def invoke_model(self, *, modelId: str, body: str, **kwargs):
        self.calls.append({"modelId": modelId, "body": body})
        if self._error is not None:
            raise self._error
        return {"body": _FakeBedrockBody(self._response_body)}


class TestValidResponse:
    @pytest.mark.asyncio
    async def test_valid_claude_style_response_is_parsed(self):
        client = _FakeBedrockClient(
            response_body={
                "content": [
                    {"text": json.dumps({"findings": [], "recommendations": []})}
                ]
            }
        )
        analyzer = BedrockAnalyzer(client=client)

        result = await analyzer.analyze(_ctx())

        assert result.analysis_unavailable is False
        assert len(client.calls) == 1


class TestInferenceUsage:
    """Fase 10 (.cursor/specs/fase10.spec.md, secao 3.4)."""

    @pytest.mark.asyncio
    async def test_usage_tokens_are_extracted_from_response(self):
        client = _FakeBedrockClient(
            response_body={
                "content": [{"text": json.dumps({"findings": [], "recommendations": []})}],
                "usage": {"input_tokens": 250, "output_tokens": 80},
            }
        )
        analyzer = BedrockAnalyzer(client=client)

        result = await analyzer.analyze(_ctx())

        assert result.usage is not None
        assert result.usage.backend == InferenceBackend.BEDROCK
        assert result.usage.prompt_tokens == 250
        assert result.usage.completion_tokens == 80
        assert result.usage.compute_seconds is None

    @pytest.mark.asyncio
    async def test_missing_usage_payload_yields_none_tokens(self):
        client = _FakeBedrockClient(
            response_body={
                "content": [{"text": json.dumps({"findings": [], "recommendations": []})}]
            }
        )
        analyzer = BedrockAnalyzer(client=client)

        result = await analyzer.analyze(_ctx())

        assert result.usage is not None
        assert result.usage.prompt_tokens is None
        assert result.usage.completion_tokens is None


class TestInfrastructureFailure:
    @pytest.mark.asyncio
    async def test_client_exception_yields_analysis_unavailable_without_raising(self):
        client = _FakeBedrockClient(error=RuntimeError("throttled"))
        analyzer = BedrockAnalyzer(client=client)

        result = await analyzer.analyze(_ctx())

        assert result.analysis_unavailable is True
        assert result.usage is None

    @pytest.mark.asyncio
    async def test_malformed_response_shape_yields_analysis_unavailable(self):
        client = _FakeBedrockClient(response_body={"unexpected": "shape"})
        analyzer = BedrockAnalyzer(client=client)

        result = await analyzer.analyze(_ctx())

        assert result.analysis_unavailable is True
        assert result.usage is None
