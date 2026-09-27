"""Fase 7 — testes golden do OllamaAnalyzer. Ver .cursor/specs/fase7.spec.md,
secao 7.

Requer Ollama real (Qwen2.5, `ollama pull qwen2.5:7b-instruct`) rodando
localmente em OLLAMA_BASE_URL (padrao http://localhost:11434). Mesmo
espirito de tests/integration/context_broker/test_orion_adapter_integration.py
(Fase 4): nao roda no ambiente de sandbox usado para desenvolver esta fase
(sem Ollama ali) — rode localmente com:

    ollama pull qwen2.5:7b-instruct
    ollama serve  # se ainda nao estiver rodando
    pip install -e ".[dev]"
    pytest -m golden tests/golden/test_semantic_analyzer_golden.py -v

IMPORTANTE, porque e' LLM: o snapshot (tests/golden/snapshots/*.json) nunca
compara texto livre (`rationale`, `message`) byte a byte — mesmo em
temperatura baixa, a prosa pode variar entre execucoes. Compara FORMA:
quais `rule`/`attribute_path`/`action` apareceram. Uma mudanca de prompt ou
de versao do modelo que altere a forma da resposta (nao so' a prosa) e' o
que este teste existe para pegar.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.ports.knowledge_retriever_port import KnowledgeCategory, RetrievedChunk
from auditor.domain.ports.semantic_analyzer_port import SemanticAnalysisContext
from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.llm.ollama_analyzer import OllamaAnalyzer

pytestmark = pytest.mark.golden

_SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"


def _temp_temperature_streetlight_ctx() -> SemanticAnalysisContext:
    """Cenario principal do plano geral e de todo o spec da Fase 7: entidade
    com `temp` (nao reconhecido pelo schema) e `temperature` (obrigatorio,
    ausente) — o Nivel 1 sozinho so' consegue dizer "temperature ausente";
    o Nivel 2 deveria reconhecer que `temp` e' provavelmente `temperature`
    com o nome errado."""
    return SemanticAnalysisContext(
        entity_id="urn:ngsi-ld:Streetlight:golden-1",
        entity_type=EntityType("Streetlight"),
        plain_values={
            "id": "urn:ngsi-ld:Streetlight:golden-1",
            "type": "Streetlight",
            "temp": 21.5,
        },
        schema={
            "required": ["temperature"],
            "additionalProperties": True,
            "properties": {"temperature": {"type": "number"}},
        },
        structural_violations=(
            Violation(
                attribute_path="temperature",
                severity=ViolationSeverity.ERROR,
                rule="required_property_missing",
                expected="present",
                found="absent",
                message="Propriedade obrigatoria 'temperature' esta ausente.",
                detected_by=DetectionSource.STRUCTURAL,
            ),
        ),
        knowledge_chunks=(
            RetrievedChunk(
                chunk_id="synonym-temperature",
                category=KnowledgeCategory.SYNONYM_GLOSSARY,
                content=(
                    "O atributo canonico e' 'temperature'. Tambem visto "
                    "como: temp, tempC, temperatura."
                ),
                similarity=0.95,
                tags=(),
            ),
        ),
    )


def _shape(result) -> dict:
    return {
        "recommendation_actions": sorted({r.action.value for r in result.recommendations}),
        "recommendation_attribute_paths": sorted({r.attribute_path for r in result.recommendations}),
    }


@pytest.fixture
def analyzer() -> OllamaAnalyzer:
    settings = Settings()
    return OllamaAnalyzer(
        client=httpx.AsyncClient(),
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )


class TestTempTemperatureCase:
    @pytest.mark.asyncio
    async def test_detects_rename_attribute_for_the_temp_synonym_case(self, analyzer):
        snapshot = json.loads(
            (_SNAPSHOTS_DIR / "temp_temperature_streetlight.json").read_text(encoding="utf-8")
        )

        result = await analyzer.analyze(_temp_temperature_streetlight_ctx())

        assert result.analysis_unavailable is False
        assert "rename_attribute" in {r.action.value for r in result.recommendations}
        matching = [
            r
            for r in result.recommendations
            if r.action.value == "rename_attribute"
            and r.attribute_path in snapshot["expected_recommendation_attribute_paths_any_of"]
        ]
        assert matching, (
            f"Esperava uma Recommendation rename_attribute com attribute_path em "
            f"{snapshot['expected_recommendation_attribute_paths_any_of']}, "
            f"recebido: {result.recommendations}"
        )

    @pytest.mark.asyncio
    async def test_response_shape_is_stable_across_two_runs(self, analyzer):
        first = await analyzer.analyze(_temp_temperature_streetlight_ctx())
        second = await analyzer.analyze(_temp_temperature_streetlight_ctx())

        assert _shape(first) == _shape(second)
