"""Motor do modo chat: análise SLM, conversa e FIWARE sob demanda."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import structlog
from rich.console import Console
from rich.table import Table

from context_broker_agent.config import get_settings
from context_broker_agent.core.intent_router import IntentRouter
from context_broker_agent.models.intent import ChatIntent, ChatTurnAnalysis
from context_broker_agent.models.messages import AgentMessage, AgentResponse
from context_broker_agent.services.fiware_client import FiwareClient, FiwareError
from context_broker_agent.services.slm_service import SLMService, SLMUnavailableError
from context_broker_agent.utils.history_manager import HistoryManager
from context_broker_agent.utils.thinking_status import ThinkingStatus
from context_broker_agent.agents.route import RouteDispatcher
from context_broker_agent.agents.analyze import AnalyzeHandler

logger = structlog.get_logger(__name__)


@dataclass
class ChatTurnResult:
    """Resultado de um turno do chat."""

    kind: str  # message | error | command
    summary: str
    analysis: ChatTurnAnalysis | None = None
    intent: ChatIntent | None = None
    agent_response: AgentResponse | None = None


class ChatEngine:
    """Gerencia histórico, SLM e execução no FIWARE apenas quando necessário."""

    def __init__(
        self,
        slm: SLMService | None = None,
        router: IntentRouter | None = None,
        history: HistoryManager | None = None,
        console: Console | None = None,

    ) -> None:
        settings = get_settings()
        self._slm = slm or SLMService()
        self._client = FiwareClient()
        self._router = router or IntentRouter(client=self._client)
        self._history = history or HistoryManager(max_turns=settings.chat_history_max_turns)
        self._console = console or Console()
        self._status = ThinkingStatus(self._console)
        self._route_dispatcher = RouteDispatcher()
        self._analyze_handler = AnalyzeHandler()


    @property
    def history(self) -> HistoryManager:
        return self._history

    @property
    def slm(self) -> SLMService:
        return self._slm

    @property
    def router(self) -> IntentRouter:
        return self._router

    async def process_user_input(self, text: str) -> ChatTurnResult:
        """Analisa com SLM; conversa, esclarece ou executa agentes FIWARE."""
        stripped = text.strip()
        if not stripped:
            return ChatTurnResult(kind="message", summary="(entrada vazia)")

        logger.debug("chat_user_input", text=stripped[:200])

        try:
            self._status.start("Pensando...")
            self._status.update("Interpretando linguagem natural...")

            try:
                analysis = await self._slm.analyze_chat_turn(
                    stripped,
                    context_messages=self._history.context_for_slm(),
                    last_intent=self._history.last_intent(),
                    pending=self._history.get_pending(),
                )
            except SLMUnavailableError:
                analysis = self._route_dispatcher.classify(stripped, self._history.last_intent(), self._history.get_pending(), self._history.context_for_slm())

            if analysis.response_type == "conversation":
                self._status.stop()
                self._print_assistant(analysis.assistant_message)
                self._history.clear_pending()
                self._history.add(stripped, analysis.assistant_message)
                return ChatTurnResult(
                    kind="message",
                    summary=analysis.assistant_message,
                    analysis=analysis,
                )

            if analysis.response_type == "clarify" or analysis.needs_clarification():
                self._status.update("Preparando pergunta de esclarecimento...")
                self._status.stop()
                msg = analysis.assistant_message or self._default_clarify_message(analysis)
                self._print_assistant(msg, style="yellow")
                self._history.set_pending(analysis.model_dump(exclude_none=True))
                self._history.add(stripped, msg)
                return ChatTurnResult(kind="message", summary=msg, analysis=analysis)

            self._history.clear_pending()
            intent = analysis.to_fiware_intent(stripped)

            self._status.update("Planejando ação no Context Broker...")
            self._status.stop()

            self._console.print(f"[dim]{analysis.assistant_message}[/dim]")
            self._print_fiware_intent(intent)

            self._status.start("Consultando Orion (NGSI-v2)...")
            try:
                response = await self._router.route(intent, stripped)
            except FiwareError as exc:
                self._status.stop()
                summary = (
                    "Não consegui acessar o Orion (FIWARE). "
                    "Inicie o broker: docker compose up -d"
                )
                self._console.print(f"[red]{summary}[/red]")
                self._history.add(stripped, summary, intent)
                return ChatTurnResult(
                    kind="error",
                    summary=summary,
                    analysis=analysis,
                    intent=intent,
                )

            self._status.update("Analisando resultados...")
            self._status.stop()

            analyze_message = AgentMessage(
                content=stripped,
                metadata={"operation": intent.operation, "agent_response": response},
            )
            response = await self._analyze_handler.execute_with_timeout(analyze_message)

            if not response.success and "Cannot connect" in response.message:
                summary = (
                    "Orion indisponível em localhost:1026. "
                    "Execute: docker compose up -d && python scripts/seed_orion.py"
                )
                self._console.print(f"[red]{summary}[/red]")
                self._history.add(stripped, summary, intent)
                return ChatTurnResult(
                    kind="error",
                    summary=summary,
                    analysis=analysis,
                    intent=intent,
                )

            summary = self._format_fiware_response(response)
            full_summary = f"{analysis.assistant_message} {summary}".strip()
            self._history.add(stripped, full_summary, intent)
            return ChatTurnResult(
                kind="message",
                summary=full_summary,
                analysis=analysis,
                intent=intent,
                agent_response=response,
            )
        except Exception:
            self._status.stop()
            raise

    def _print_assistant(self, message: str, style: str = "green") -> None:
        self._console.print(f"\n[bold {style}]DKRT[/bold {style}] {message}\n")

    def _print_fiware_intent(self, intent: ChatIntent) -> None:
        self._console.print(
            f"[cyan]→[/cyan] [bold]{intent.operation}[/bold] "
            f"[dim]({intent.confidence:.0%} · {intent.source})[/dim] "
            f"{intent.summary()}"
        )

    @staticmethod
    def _default_clarify_message(analysis: ChatTurnAnalysis) -> str:
        missing = ", ".join(analysis.missing_fields) if analysis.missing_fields else "mais detalhes"
        return f"Preciso de {missing} para continuar. Pode informar?"

    def _format_fiware_response(self, response: AgentResponse) -> str:
        if response.success:
            self._console.print(f"[green]✓[/green] {response.message}")
        else:
            self._console.print(f"[red]✗[/red] {response.message}")

        entities = response.data.get("entities")
        if isinstance(entities, list) and entities:
            self._print_entities_table(entities)
            return f"{response.message}; {len(entities)} registro(s)"

        entity = response.data.get("entity")
        if entity:
            self._console.print(f"[dim]{entity}[/dim]")

        return response.message

    def _print_entities_table(self, entities: list[dict[str, Any]]) -> None:
        table = Table(title="Entidades NGSI-v2", border_style="dim")
        table.add_column("ID")
        table.add_column("Tipo")
        table.add_column("Atributos")
        for ent in entities[:25]:
            eid = str(ent.get("id", ""))
            etype = str(ent.get("type", ""))
            attrs = {k: v for k, v in ent.items() if k not in ("id", "type")}
            summary = ", ".join(f"{k}" for k in list(attrs.keys())[:4]) or "-"
            table.add_row(eid, etype, summary)
        self._console.print(table)
        if len(entities) > 25:
            self._console.print(f"[dim]... +{len(entities) - 25} entidade(s)[/dim]")

    async def status(self) -> dict[str, Any]:
        ollama = await self._slm.check_ollama()
        fiware = await self._client.check_health()
        return {"ollama": ollama, "fiware": fiware, "model": self._slm.current_model}

    async def print_startup_hints(self) -> None:
        """Avisos ao abrir o chat (/status para detalhes)."""
        try:
            info = await self.status()
        except Exception:
            self._console.print(
                "[yellow]! Não consegui verificar Ollama/Orion no startup.[/yellow]"
            )
            return

        ollama_info = info["ollama"]
        reachable = bool(ollama_info.get("installed_models")) or ollama_info.get(
            "model_available"
        )
        if not reachable:
            self._console.print(
                "[yellow]! Ollama offline em "
                f"{ollama_info.get('base_url', 'localhost:11434')} — sem SLM, respostas "
                "ficarão simplificadas. Suba com:[/yellow] [bold]ollama serve[/bold]"
            )
        elif not ollama_info.get("model_available"):
            installed = ", ".join(ollama_info.get("installed_models", [])) or "nenhum"
            self._console.print(
                f"[yellow]! Modelo {ollama_info.get('configured_model')} ausente. "
                f"Instalados: {installed}. Use /model <nome>.[/yellow]"
            )

        if not info["fiware"].get("ok"):
            self._console.print(
                "[yellow]! Orion offline — conversa OK; dados exigem docker compose up -d[/yellow]"
            )


def configure_quiet_logging() -> None:
    """Oculta logs INFO/WARNING no terminal (mantém ERROR/CRITICAL).

    O motor de chat já trata fallbacks (SLM offline, Orion offline) com mensagens
    amigáveis; logs estruturados poluiriam a UX.
    """
    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    for name in (
        "context_broker_agent",
        "context_broker_agent.services.slm_service",
        "context_broker_agent.services.ollama_client",
        "context_broker_agent.services.fiware_client",
        "context_broker_agent.core.intent_router",
        "aiohttp",
        "asyncio",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
    )