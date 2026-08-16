"""RouteDispatcher — classifica intenção e papéis dos agentes."""

import re

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse
from context_broker_agent.models.intent import ChatIntent, ChatTurnAnalysis
from context_broker_agent.utils.chat_turn_classifier import requires_fiware_action

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


class RouteDispatcher(BaseAgent):
    name = "route"

    async def process(self, message: AgentMessage) -> AgentResponse:
        text = message.content.lower()
        intent = message.metadata.get("intent", "query")

        if any(w in text for w in ("criar", "create", "cadastrar", "inserir")):
            intent = "create"
        elif any(w in text for w in ("inscrever", "subscribe", "avisar", "notificar")):
            intent = "subscribe"
        elif any(w in text for w in ("analisar", "resumir", "analyze")):
            intent = "analyze"

        roles = {
            "query": ["query", "analyze"],
            "create": ["create", "route"],
            "subscribe": ["subscribe", "route"],
            "analyze": ["analyze", "query"],
        }
        active = roles.get(intent, ["query", "route", "create", "subscribe", "analyze"])

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message=f"Intenção classificada: {intent}",
            data={"intent": intent, "active_agents": active},
        )

    def classify(
        self,
        text: str,
        last_intent: ChatIntent | None,
        pending: dict | None,
        context_messages: list[dict[str, str]] | None = None,
    ) -> ChatTurnAnalysis:
        """Fallback determinístico (ADR-0007): usado pelo ChatEngine quando o
        SLM está indisponível (SLMUnavailableError). Classifica por palavra-chave,
        sem depender de modelo."""
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

        if any(w in lower for w in ("provisionar", "provisione", "provisionamento")) or (
            "dispositivo" in lower and ("mqtt" in lower or "iot" in lower)
        ):
            device_id = self._extract_entity_id(text)
            etype = device_id.split(":")[0] if device_id else "Device"
            return ChatTurnAnalysis(
                response_type="fiware",
                assistant_message=f"Vou provisionar o dispositivo {device_id or etype} no IoT Agent.",
                operation="iot_provision",
                entity_type=etype,
                entity_id=device_id,
                confidence=0.75,
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
    def _has_fiware_keywords(text: str) -> bool:
        return any(k in text for k in FIWARE_KEYWORDS)

    @staticmethod
    def _is_conversation_only(text: str) -> bool:
        if RouteDispatcher._has_fiware_keywords(text):
            return False
        if any(h in text for h in CONVERSATION_HINTS):
            return True
        return len(text.split()) <= 3 and not RouteDispatcher._has_fiware_keywords(text)

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

    @staticmethod
    def _extract_entity_id(text: str) -> str | None:
        # TODO(dívida técnica): duplicado de SLMService._extract_entity_id
        # (que ainda precisa dele para o fluxo interpret_query/_interpret_heuristic).
        # Extrair para um utilitário compartilhado (ex.: utils/text_extraction.py)
        # quando for fazer a limpeza final do módulo utils.
        match = re.search(r"([A-Za-z][\w-]*:[\w.-]+)", text)
        return match.group(1) if match else None

        