"""SLMService — interpretação NL via Ollama (Qwen2.5), phi-2 ou heurística."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from context_broker_agent.config import get_settings
from context_broker_agent.models.intent import ChatIntent, ChatTurnAnalysis
from context_broker_agent.models.ngsi import NgsiEntity, NgsiQueryParams, SlmInterpretation
from context_broker_agent.services.llama_cpp_service import (
    LlamaCppClient,
    LlamaCppError,
)
from context_broker_agent.services.ollama_client import OllamaClient, OllamaError
from context_broker_agent.utils.chat_turn_classifier import (
    apply_conversation_guard,
    requires_fiware_action,
)
from context_broker_agent.utils.ngsi_filters import (
    normalize_entity_type,
    normalize_ngsi_q,
)

logger = logging.getLogger(__name__)

NGSI_SYSTEM_PROMPT = """Você é um assistente DKRT para FIWARE Orion Context Broker (NGSI-v2).
Converta o pedido do usuário em JSON estrito com este formato:
{
  "intent": "query|provision|subscribe|analyze",
  "ngsi_query": {"type": "Sensor", "limit": 20, "id": null, "q": null},
  "entity": null
}
Para provision, preencha entity: {"id": "Tipo:id", "type": "Tipo", "attrs": {}}.
Para subscribe ou query, use ngsi_query.type (ex.: Sensor, Device).
Responda APENAS com o JSON, sem markdown."""

CHAT_ANALYSIS_PROMPT = """Você é o DKRT, um assistente inteligente especializado em FIWARE Orion
Context Broker (NGSI-v2). Você conversa naturalmente em português brasileiro, com tom
amigável, claro e direto — como um colega técnico, sem clichês ou frases padronizadas.

Suas capacidades reais:
- Conversar e explicar conceitos (NGSI-v2, sensores, entidades, agentes multiagentes).
- Consultar/listar/criar/atualizar/remover entidades no Orion via agentes especializados.
- Auxiliar com diagnóstico (Orion online/offline, modelo do SLM).
- NÃO faz persistência histórica de valores (isso seria função do QuantumLeap/STH-Comet,
  não do Orion puro). Seja honesto se o usuário perguntar.

Responda SEMPRE em JSON válido com este schema:

{
  "response_type": "conversation|fiware|clarify",
  "assistant_message": "texto natural em português, com 1-4 frases ricas",
  "operation": null,
  "entity_type": null,
  "entity_id": null,
  "attribute": null,
  "ngsi_q": null,
  "missing_fields": [],
  "confidence": 0.0
}

REGRAS de classificação:
1. conversation — cumprimentos, perguntas conceituais ("o que é NGSI?", "você persiste
   dados?"), explicações, diagnóstico, reações ("que saco"), follow-ups sobre status.
   assistant_message: resposta natural, específica ao que foi perguntado. NUNCA repita
   a mesma frase padrão; varie a forma com base no contexto. operation=null.

2. fiware — SOMENTE quando o usuário pede AÇÃO no broker: listar, consultar, criar,
   atualizar, apagar entidades. Ex.: "listar sensores", "mostrar sensores do lab 64".
   NÃO use fiware para perguntas conceituais ou reclamações.

3. clarify — ação FIWARE com dados faltantes; faça pergunta específica.

ngsi_q: SOMENTE expressão NGSI-v2 (ex.: lab==64). NUNCA JSON nem URL.
entity_type: nome capitalizado (Sensor, Device, Room).

Confidence: 0.0–1.0 (sua certeza na classificação)."""

FIWARE_KEYWORDS = (
    "sensor", "sensores", "entidade", "entidades", "orion", "fiware", "broker",
    "listar", "consultar", "mostrar", "criar", "cadastrar", "atualizar", "apagar",
    "lab", "laboratório", "ngsi", "device", "dispositivo", "temperatura", "umidade",
    "context broker", "subscribe", "inscrever",
)

CONVERSATION_HINTS = (
    "ola", "olá", "oi", "bom dia", "boa tarde", "boa noite", "hey", "hello", "hi",
    "e aí", "eai", "obrigado", "obrigada", "valeu", "tchau", "até", "quem é você",
    "o que você", "ajuda", "help",
)


class SLMService:
    """Converte linguagem natural em intent + parâmetros NGSI.

    Suporta três backends (selecionados por SLM_PROVIDER):
    - ollama      → daemon HTTP local (bom em desenvolvimento)
    - llama_cpp   → llama.cpp via binding Python (in-process, distribuível)
    - transformers→ phi-2 via HuggingFace (legado)
    Sem SLM_ENABLED ou em erro, cai na heurística determinística.
    """

    def __init__(
        self,
        ollama: OllamaClient | None = None,
        llama_cpp: LlamaCppClient | None = None,
    ) -> None:
        self._settings = get_settings()
        self._ollama = ollama
        self._llama_cpp = llama_cpp
        self._model_override: str | None = None
        self._model = None
        self._tokenizer = None

    @property
    def provider(self) -> str:
        return self._settings.slm_provider.lower()

    @property
    def current_model(self) -> str:
        if self._model_override:
            return self._model_override
        if self.provider == "llama_cpp":
            return (self._llama_cpp or LlamaCppClient()).model
        return (self._ollama or OllamaClient()).model

    def set_model(self, name: str) -> None:
        """Altera modelo em runtime (modo chat). Para llama_cpp é informativo."""
        self._model_override = name
        if self._ollama:
            self._ollama.model = name

    def _ollama_client(self) -> OllamaClient:
        client = self._ollama or OllamaClient()
        if self._model_override:
            client.model = self._model_override
        return client

    def _llama_cpp_client(self) -> LlamaCppClient:
        if self._llama_cpp is None:
            self._llama_cpp = LlamaCppClient()
        return self._llama_cpp

    def interpret_query(self, text: str) -> SlmInterpretation:
        """Interpreta texto conforme SLM_PROVIDER e SLM_ENABLED."""
        settings = get_settings()
        if not settings.slm_enabled:
            return self._interpret_heuristic(text)

        provider = settings.slm_provider.lower()
        try:
            if provider == "ollama":
                return self._interpret_ollama(text)
            if provider == "llama_cpp":
                return self._interpret_llama_cpp(text)
            if provider == "transformers":
                return self._interpret_phi2(text)
        except Exception as exc:
            logger.warning("SLM falhou (%s), usando heurística: %s", provider, exc)

        return self._interpret_heuristic(text)

    def _interpret_ollama(self, text: str) -> SlmInterpretation:
        client = self._ollama or OllamaClient()
        raw = asyncio.run(client.chat(system=NGSI_SYSTEM_PROMPT, user=text))
        return self._parse_llm_json(raw, source="ollama")

    def _interpret_llama_cpp(self, text: str) -> SlmInterpretation:
        client = self._llama_cpp_client()
        raw = asyncio.run(client.chat(system=NGSI_SYSTEM_PROMPT, user=text))
        return self._parse_llm_json(raw, source="llama_cpp")

    def _parse_llm_json(self, raw: str, source: str) -> SlmInterpretation:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise OllamaError("JSON não encontrado na resposta do modelo")
        data = json.loads(match.group())
        intent = data.get("intent", "query")
        ngsi_query = None
        entity = None
        if data.get("ngsi_query"):
            ngsi_query = NgsiQueryParams.model_validate(data["ngsi_query"])
        if data.get("entity"):
            entity = NgsiEntity.model_validate(data["entity"])
        return SlmInterpretation(
            intent=intent,
            ngsi_query=ngsi_query,
            entity=entity,
            raw_interpretation=raw,
            source=source,
        )

    def _interpret_heuristic(self, text: str) -> SlmInterpretation:
        lower = text.lower()

        if any(w in lower for w in ("criar", "cadastrar", "provisionar", "inserir")):
            entity_id = self._extract_entity_id(text) or "Device:99"
            entity_type = entity_id.split(":")[0]
            return SlmInterpretation(
                intent="provision",
                entity=NgsiEntity(id=entity_id, type=entity_type, attrs={"status": {"value": "active"}}),
                raw_interpretation=f"Heurística: provisionar {entity_id}",
                source="heuristic",
            )

        if any(w in lower for w in ("inscrever", "avisar", "notificar", "subscribe")):
            return SlmInterpretation(
                intent="subscribe",
                ngsi_query=NgsiQueryParams(type="Sensor"),
                raw_interpretation="Heurística: planejar subscrição",
                source="heuristic",
            )

        entity_type = "Sensor"
        if "device" in lower or "dispositivo" in lower:
            entity_type = "Device"

        return SlmInterpretation(
            intent="query",
            ngsi_query=NgsiQueryParams(type=entity_type, limit=20),
            raw_interpretation=f"Heurística: consultar type={entity_type}",
            source="heuristic",
        )

    def _interpret_phi2(self, text: str) -> SlmInterpretation:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if self._model is None:
            self._tokenizer = AutoTokenizer.from_pretrained(self._settings.slm_model, trust_remote_code=True)
            self._model = AutoModelForCausalLM.from_pretrained(
                self._settings.slm_model,
                trust_remote_code=True,
                torch_dtype=torch.float32,
            )

        prompt = (
            "Converta o pedido em JSON com intent e ngsi_query:\n"
            f'Pedido: "{text}"\nJSON:'
        )
        inputs = self._tokenizer(prompt, return_tensors="pt")
        outputs = self._model.generate(**inputs, max_new_tokens=128)
        raw = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
        return self._parse_llm_json(raw, source="phi-2")

    async def analyze_chat_turn(
        self,
        text: str,
        context_messages: list[dict[str, str]] | None = None,
        last_intent: ChatIntent | None = None,
        pending: dict | None = None,
    ) -> ChatTurnAnalysis:
        """Classifica turno: conversa, FIWARE ou pedido de esclarecimento."""
        settings = get_settings()
        ctx = context_messages or []
        provider = settings.slm_provider.lower()
        if settings.slm_enabled and provider in ("ollama", "llama_cpp"):
            try:
                analysis = await self._analyze_chat_llm(
                    text, ctx, pending, last_intent, provider
                )
                analysis = apply_conversation_guard(text, analysis, ctx)
                return self._normalize_fiware_analysis(analysis, text)
            except Exception as exc:
                logger.debug("SLM análise falhou, heurística: %s", exc)
        analysis = self._analyze_chat_heuristic(text, last_intent, pending, ctx)
        analysis = apply_conversation_guard(text, analysis, ctx)
        return self._normalize_fiware_analysis(analysis, text)

    async def interpret_chat_intent(
        self,
        text: str,
        context_messages: list[dict[str, str]] | None = None,
        last_intent: ChatIntent | None = None,
    ) -> ChatIntent:
        """Compat: retorna intent apenas se o turno for ação FIWARE."""
        analysis = await self.analyze_chat_turn(text, context_messages, last_intent)
        if analysis.response_type == "fiware" and not analysis.needs_clarification():
            return analysis.to_fiware_intent(text)
        return ChatIntent(operation="query", entity_type="Sensor", confidence=0.3, source="heuristic")

    async def _analyze_chat_llm(
        self,
        text: str,
        context_messages: list[dict[str, str]],
        pending: dict | None,
        last_intent: ChatIntent | None,
        provider: str,
    ) -> ChatTurnAnalysis:
        """Caminho comum para Ollama e llama_cpp — ambos com interface chat_messages."""
        if provider == "llama_cpp":
            client = self._llama_cpp_client()
            source = "llama_cpp"
        else:
            client = self._ollama_client()
            source = "ollama"

        system = CHAT_ANALYSIS_PROMPT
        if last_intent:
            system += f"\nÚltima ação FIWARE (contexto): {last_intent.summary()}"
        if pending:
            system += (
                "\nContexto pendente (complete com a nova mensagem): "
                f"{json.dumps(pending, ensure_ascii=False)}"
            )
        messages = [{"role": "system", "content": system}]
        messages.extend(context_messages)
        messages.append({"role": "user", "content": text})
        raw = await client.chat_messages(messages, json_mode=True)
        return self._parse_chat_analysis(raw, source=source)

    @staticmethod
    def _normalize_fiware_analysis(analysis: ChatTurnAnalysis, user_text: str) -> ChatTurnAnalysis:
        if analysis.response_type != "fiware":
            return analysis
        return analysis.model_copy(
            update={
                "entity_type": normalize_entity_type(analysis.entity_type),
                "ngsi_q": normalize_ngsi_q(analysis.ngsi_q, user_text),
            }
        )

    def _parse_chat_analysis(self, raw: str, source: str) -> ChatTurnAnalysis:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"JSON de análise não encontrado em resposta {source}")
        data = json.loads(match.group())
        rtype = data.get("response_type", "conversation")
        if rtype not in ("conversation", "fiware", "clarify"):
            rtype = "conversation"
        op = data.get("operation")
        if op and op not in ("query", "create", "update", "list", "delete"):
            op = None
        return ChatTurnAnalysis(
            response_type=rtype,
            assistant_message=data.get("assistant_message", ""),
            operation=op,
            entity_type=data.get("entity_type"),
            entity_id=data.get("entity_id"),
            attribute=data.get("attribute"),
            ngsi_q=data.get("ngsi_q"),
            missing_fields=data.get("missing_fields") or [],
            confidence=float(data.get("confidence", 0.7)),
            source=source,
        )

    @staticmethod
    def _has_fiware_keywords(text: str) -> bool:
        return any(k in text for k in FIWARE_KEYWORDS)

    @staticmethod
    def _is_conversation_only(text: str) -> bool:
        if SLMService._has_fiware_keywords(text):
            return False
        if any(h in text for h in CONVERSATION_HINTS):
            return True
        return len(text.split()) <= 3 and not SLMService._has_fiware_keywords(text)

    def _analyze_chat_heuristic(
        self,
        text: str,
        last_intent: ChatIntent | None,
        pending: dict | None,
        context_messages: list[dict[str, str]] | None = None,
    ) -> ChatTurnAnalysis:
        lower = text.lower().strip()

        if self._is_conversation_only(lower):
            return ChatTurnAnalysis(
                response_type="conversation",
                assistant_message=self._conversation_reply(lower),
                confidence=0.85,
                source="heuristic",
            )

        if pending and not self._is_conversation_only(lower):
            merged = {**pending}
            if lab := re.search(r"lab(?:orat[oó]rio)?\s*(\d+)", lower):
                merged["ngsi_q"] = f"lab=={lab.group(1)}"
            if eid := self._extract_entity_id(text):
                merged["entity_id"] = eid
            return ChatTurnAnalysis(
                response_type="fiware",
                assistant_message=merged.get("assistant_message", "Entendido, vou consultar o Orion."),
                operation=merged.get("operation", "query"),
                entity_type=merged.get("entity_type", "Sensor"),
                entity_id=merged.get("entity_id"),
                attribute=merged.get("attribute"),
                ngsi_q=merged.get("ngsi_q"),
                confidence=0.75,
                source="heuristic",
            )

        if last_intent and any(p in lower for p in ("e a", "e o", "e os", "também", "agora")):
            attr = last_intent.attribute
            if "umidade" in lower:
                attr = "humidity"
            elif "temperatura" in lower:
                attr = "temperature"
            return ChatTurnAnalysis(
                response_type="fiware",
                assistant_message="Consultando no Orion com o contexto anterior.",
                operation="query",
                entity_type=last_intent.entity_type,
                entity_id=last_intent.entity_id,
                attribute=attr,
                confidence=0.7,
                source="heuristic",
            )

        if any(w in lower for w in ("criar", "cadastrar", "inserir")):
            eid = self._extract_entity_id(text)
            etype = eid.split(":")[0] if eid else ("Device" if "device" in lower else "Sensor")
            return ChatTurnAnalysis(
                response_type="fiware",
                assistant_message=f"Vou criar a entidade {eid or etype}.",
                operation="create",
                entity_type=etype,
                entity_id=eid,
                confidence=0.75,
                source="heuristic",
            )

        if any(w in lower for w in ("atualizar", "alterar")):
            eid = self._extract_entity_id(text)
            if not eid:
                return ChatTurnAnalysis(
                    response_type="clarify",
                    assistant_message="Qual o ID da entidade? (ex.: Sensor:001)",
                    operation="update",
                    missing_fields=["entity_id"],
                    confidence=0.7,
                    source="heuristic",
                )
            return ChatTurnAnalysis(
                response_type="fiware",
                assistant_message=f"Atualizando {eid}.",
                operation="update",
                entity_id=eid,
                confidence=0.7,
                source="heuristic",
            )

        if any(w in lower for w in ("apagar", "remover", "deletar")):
            eid = self._extract_entity_id(text)
            if not eid:
                return ChatTurnAnalysis(
                    response_type="clarify",
                    assistant_message="Qual entidade devo remover? Informe o ID (ex.: Sensor:001).",
                    operation="delete",
                    missing_fields=["entity_id"],
                    source="heuristic",
                )
            return ChatTurnAnalysis(
                response_type="fiware",
                assistant_message=f"Removendo {eid}.",
                operation="delete",
                entity_id=eid,
                source="heuristic",
            )

        if self._has_fiware_keywords(lower) and requires_fiware_action(lower):
            lab_q = None
            if m := re.search(r"lab(?:orat[oó]rio)?\s*(\d+)", lower):
                lab_q = f"lab=={m.group(1)}"
            etype = "Device" if "device" in lower or "dispositivo" in lower else "Sensor"
            op = "list" if any(w in lower for w in ("listar", "lista", "mostrar", "quais")) else "query"
            if re.search(r"\bver\s+(meus?|minhas?|os|as)?\s*(sensores|entidades)", lower):
                op = "list"
            return ChatTurnAnalysis(
                response_type="fiware",
                assistant_message="Buscando dados no Context Broker Orion.",
                operation=op,
                entity_type=etype,
                ngsi_q=lab_q,
                attribute="humidity" if "umidade" in lower else None,
                confidence=0.75,
                source="heuristic",
            )

        return ChatTurnAnalysis(
            response_type="conversation",
            assistant_message=(
                "[modo simplificado — Ollama offline] "
                "Consigo executar comandos no Orion (listar/consultar/criar/atualizar/apagar "
                "sensores e entidades). Para respostas mais ricas e naturais, suba o Ollama: "
                "`ollama serve`."
            ),
            confidence=0.6,
            source="heuristic",
        )

    @staticmethod
    def _conversation_reply(lower: str) -> str:
        if "bom dia" in lower:
            return "Bom dia! Sou o assistente DKRT. Em que posso ajudar com o Context Broker?"
        if "boa tarde" in lower:
            return "Boa tarde! Como posso ajudar você hoje?"
        if "boa noite" in lower:
            return "Boa noite! Estou à disposição para consultas no Orion."
        if any(w in lower for w in ("obrigado", "obrigada", "valeu")):
            return "Por nada! Se precisar de dados dos sensores, é só pedir."
        if any(w in lower for w in ("tchau", "até")):
            return "Até logo! Use /exit para sair do chat."
        if "o que você" in lower or "quem é você" in lower:
            return (
                "Sou o DKRT: interpreto linguagem natural e, quando necessário, "
                "consulto o FIWARE Orion (NGSI-v2) pelos agentes especializados."
            )
        return "Olá! Sou o assistente DKRT. Posso ajudar com o Context Broker ou tirar dúvidas — o que você precisa?"

    async def check_ollama(self) -> dict:
        """Saúde do backend SLM atual. Nome mantido por compat com chat_engine/cli."""
        provider = self.provider
        configured = self.current_model

        if provider == "llama_cpp":
            client = self._llama_cpp_client()
            try:
                models = await client.list_models()
                available = client.model_path.exists()
                error = None
            except Exception as exc:
                models = []
                available = False
                error = str(exc)
            return {
                "provider": "llama_cpp",
                "base_url": f"file://{client.model_path}",
                "configured_model": configured,
                "model_available": available,
                "installed_models": models,
                "error": error,
            }

        client = self._ollama_client()
        try:
            models = await client.list_models()
            error = None
        except Exception as exc:
            models = []
            error = str(exc)
        return {
            "provider": "ollama",
            "base_url": client.base_url,
            "configured_model": configured,
            "model_available": any(
                m == configured or m.startswith(f"{configured}:")
                for m in models
            ),
            "installed_models": models,
            "error": error,
        }

    @staticmethod
    def _extract_entity_id(text: str) -> str | None:
        match = re.search(r"([A-Za-z][\w-]*:[\w.-]+)", text)
        return match.group(1) if match else None
