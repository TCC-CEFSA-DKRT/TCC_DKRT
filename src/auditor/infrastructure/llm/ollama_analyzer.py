"""OllamaAnalyzer — implementa SemanticAnalyzerPort contra um Qwen2.5 local
via Ollama. Ver .cursor/specs/fase7.spec.md, secao 5.

Dev/local: sem custo de API, sem dependencia de rede externa (so' o
Ollama, rodando na mesma maquina/rede). `format="json"` (recurso nativo do
Ollama para forcar saida JSON) + `temperature` baixa — determinismo e' mais
importante que criatividade aqui (mesma decisao documentada no plano geral,
secao 3.5).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import httpx

from auditor.domain.entities.entity_report import (
    InferenceBackend,
    SemanticAnalysisUsage,
)
from auditor.domain.ports.semantic_analyzer_port import (
    SemanticAnalysisContext,
    SemanticAnalysisResult,
    SemanticAnalyzerPort,
)
from auditor.infrastructure.llm.semantic_output_schema import (
    parse_semantic_analysis_output,
)

_PROMPT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "prompts" / "semantic_diagnosis.md"
)
_TEMPERATURE = 0.1


def _render_structural_violations(ctx: SemanticAnalysisContext) -> str:
    if not ctx.structural_violations:
        return "(nenhuma — analise por conta propria a partir do schema e da entidade)"
    return "\n".join(
        f"- [{v.severity.value}] {v.rule} em `{v.attribute_path}`: {v.message}"
        for v in ctx.structural_violations
    )


def _render_knowledge_chunks(ctx: SemanticAnalysisContext) -> str:
    if not ctx.knowledge_chunks:
        return "(nenhum chunk recuperado)"
    return "\n".join(
        f"- [{chunk.category.value}] {chunk.content}" for chunk in ctx.knowledge_chunks
    )


def build_prompt(ctx: SemanticAnalysisContext) -> str:
    # Substituicao por marcadores %%...%% (nunca `str.format`/f-string no
    # template inteiro): o proprio prompt contem um exemplo de JSON com
    # chaves literais ({...}) — `.format()` tentaria interpreta-las como
    # placeholders e quebraria com KeyError.
    template = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("%%ENTITY_TYPE%%", ctx.entity_type.value)
        .replace(
            "%%PLAIN_VALUES_JSON%%",
            json.dumps(ctx.plain_values, ensure_ascii=False, indent=2),
        )
        .replace("%%SCHEMA_JSON%%", json.dumps(ctx.schema, ensure_ascii=False, indent=2))
        .replace("%%STRUCTURAL_VIOLATIONS_TEXT%%", _render_structural_violations(ctx))
        .replace("%%KNOWLEDGE_CHUNKS_TEXT%%", _render_knowledge_chunks(ctx))
    )


class OllamaAnalyzer(SemanticAnalyzerPort):
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str = "qwen2.5:7b-instruct",
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def analyze(self, ctx: SemanticAnalysisContext) -> SemanticAnalysisResult:
        prompt = build_prompt(ctx)
        try:
            response = await self._client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": _TEMPERATURE},
                },
                timeout=120.0,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            # Timeout, conexao recusada, ou HTTP >=400/500 do Ollama —
            # nunca propaga (contrato da porta, secao 1): o Nivel 1 ja'
            # produziu um resultado valido e persistivel antes deste
            # ponto; uma falha aqui e' degradacao, nao erro fatal do run.
            return SemanticAnalysisResult(analysis_unavailable=True)

        body = response.json()
        raw_output = body.get("response", "")
        result = parse_semantic_analysis_output(raw_output)

        # Fase 10 (.cursor/specs/fase10.spec.md, secao 3.4): "total_duration"
        # e' o tempo total (ns) que o Ollama gastou nesta chamada (load +
        # eval) — unico numero que serve de proxy de custo computacional
        # quando nao ha billing por token (Ollama local). Ausente em
        # respostas antigas/atipicas -> None, nunca 0 inventado. Preenchido
        # mesmo quando a saida nao validou (analysis_unavailable=True): a
        # chamada respondeu e gastou o tempo de qualquer forma.
        total_duration_ns = body.get("total_duration")
        usage = SemanticAnalysisUsage(
            backend=InferenceBackend.OLLAMA,
            compute_seconds=(
                total_duration_ns / 1_000_000_000 if total_duration_ns is not None else None
            ),
        )
        return dataclasses.replace(result, usage=usage)
