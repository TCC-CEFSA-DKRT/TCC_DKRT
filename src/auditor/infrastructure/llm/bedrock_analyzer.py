"""BedrockAnalyzer — implementa SemanticAnalyzerPort via AWS Bedrock. Ver
.cursor/specs/fase7.spec.md, secao 6.

Escopo desta fase e' so' a FORMA: o suficiente para `container.py` (secao
7) poder alternar entre Ollama e Bedrock via configuracao, sem mudar
`RunAuditUseCase` — mesmo motivo de "duas implementacoes desde o inicio"
ja' usado em `JobQueuePort` (Fase 5: LocalJobQueue/SqsJobQueue). A decisao
final entre Bedrock e Ollama em EC2 para producao, e testes de integracao
contra AWS real, ficam para a Fase 9 (com o orcamento do AWS Academy
Learner Lab em maos — plano geral, Parte VII "Ainda em aberto").

Reaproveita o mesmo prompt (`ollama_analyzer.build_prompt`) e a mesma
validacao de saida (`semantic_output_schema.parse_semantic_analysis_output`)
do OllamaAnalyzer — a unica diferenca entre os dois adaptadores e' COMO a
inferencia e' invocada, nunca o que conta como uma saida valida.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Protocol

from auditor.domain.entities.entity_report import (
    InferenceBackend,
    SemanticAnalysisUsage,
)
from auditor.domain.ports.semantic_analyzer_port import (
    SemanticAnalysisContext,
    SemanticAnalysisResult,
    SemanticAnalyzerPort,
)
from auditor.infrastructure.llm.ollama_analyzer import build_prompt
from auditor.infrastructure.llm.semantic_output_schema import (
    parse_semantic_analysis_output,
)

_DEFAULT_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"


class _BedrockRuntimeClient(Protocol):
    """Subconjunto de `boto3.client("bedrock-runtime")` que este adaptador
    usa — Protocol em vez de depender do tipo concreto do boto3, para que
    os testes desta fase (secao 6: "forma", sem AWS real) possam injetar
    um fake sem instalar/mocking pesado do boto3 inteiro."""

    def invoke_model(self, *, modelId: str, body: str, **kwargs: Any) -> dict: ...


class BedrockAnalyzer(SemanticAnalyzerPort):
    def __init__(self, client: _BedrockRuntimeClient, model_id: str = _DEFAULT_MODEL_ID) -> None:
        self._client = client
        self._model_id = model_id

    async def analyze(self, ctx: SemanticAnalysisContext) -> SemanticAnalysisResult:
        prompt = build_prompt(ctx)
        try:
            # boto3 e' sincrono; despachado em thread para nao bloquear o
            # event loop (mesmo padrao de SqsJobQueue, Fase 5).
            import asyncio

            response = await asyncio.to_thread(
                self._client.invoke_model,
                modelId=self._model_id,
                body=json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 2048,
                        "temperature": 0.1,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ),
            )
        except Exception:
            # Qualquer falha de infraestrutura AWS (credenciais, throttling,
            # rede, modelo indisponivel na regiao) e' degradacao, nunca
            # propaga (mesmo contrato do OllamaAnalyzer, secao 1/5).
            return SemanticAnalysisResult(analysis_unavailable=True)

        try:
            payload = json.loads(response["body"].read())
            raw_output = payload["content"][0]["text"]
        except (KeyError, IndexError, ValueError, json.JSONDecodeError):
            return SemanticAnalysisResult(analysis_unavailable=True)

        result = parse_semantic_analysis_output(raw_output)

        # Fase 10 (.cursor/specs/fase10.spec.md, secao 3.4): a API de
        # mensagens da Anthropic no Bedrock devolve `usage.input_tokens`/
        # `output_tokens` no payload — ausente (formato de resposta
        # inesperado) -> None, nunca 0 inventado.
        usage_payload = payload.get("usage") or {}
        usage = SemanticAnalysisUsage(
            backend=InferenceBackend.BEDROCK,
            prompt_tokens=usage_payload.get("input_tokens"),
            completion_tokens=usage_payload.get("output_tokens"),
        )
        return dataclasses.replace(result, usage=usage)
