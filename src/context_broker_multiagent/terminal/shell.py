"""Terminal CLI externo DKRT — shell interativo principal."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING

import structlog
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table

from context_broker_multiagent.config import PROJECT_ROOT
from context_broker_multiagent.core.chat_engine import ChatEngine
from context_broker_multiagent.models.ngsi import NgsiQueryParams
from context_broker_multiagent.orchestrator import MultiAgentOrchestrator
from context_broker_multiagent.services.fiware_client import FiwareClient
from context_broker_multiagent.terminal.commands import TERMINAL_COMMANDS, build_command_map

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

PROMPT_LABEL = "dkrt> "

COMPLETER = WordCompleter(
    [
        "/help",
        "/exit",
        "/quit",
        "/clear",
        "/history",
        "/status",
        "/agents",
        "/model",
        "/query",
        "/orchestrate",
    ],
    ignore_case=True,
)


class DkrtTerminal:
    """Shell de terminal dedicado (estilo Ollama / Claude CLI)."""

    def __init__(self) -> None:
        load_dotenv()
        self.console = Console()
        self.engine = ChatEngine(console=self.console)
        self._cmd_map = build_command_map()
        self._history_path = PROJECT_ROOT / ".dkrt_terminal_history"
        self._session: PromptSession | None = None

    def _get_session(self) -> PromptSession:
        if self._session is None:
            self._session = PromptSession(
                history=FileHistory(str(self._history_path)),
                auto_suggest=AutoSuggestFromHistory(),
                completer=COMPLETER,
                multiline=False,
            )
        return self._session

    async def run(self) -> None:
        """Loop principal do terminal até /exit."""
        self._print_banner()
        await self.engine.print_startup_hints()
        self.console.print("[dim]Digite em linguagem natural ou /help para comandos.[/dim]\n")

        while True:
            try:
                line = await self._read_line()
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[yellow]Sessão encerrada.[/yellow]")
                break

            text = line.strip()
            if not text:
                continue

            if self._is_terminal_command(text):
                if await self._dispatch_command(text):
                    break
                continue

            try:
                await self.engine.process_user_input(text)
            except Exception as exc:
                logger.exception("terminal_turn_error")
                self.console.print(f"[red]Erro:[/red] {exc}")

    async def _read_line(self) -> str:
        first = await self._get_session().prompt_async(PROMPT_LABEL)
        stripped = first.strip()
        if stripped.startswith("{") and not stripped.endswith("}"):
            lines = [first]
            self.console.print("[dim]JSON multilinha — Enter vazio para enviar[/dim]")
            while True:
                extra = await self._get_session().prompt_async("... ")
                if not extra.strip():
                    break
                lines.append(extra)
            return "\n".join(lines)
        return first

    @staticmethod
    def _is_terminal_command(text: str) -> bool:
        return text.startswith("/") or text.startswith(":")

    def _parse_command(self, text: str) -> tuple[str, str]:
        raw = text.lstrip("/:").strip()
        parts = raw.split(maxsplit=1)
        name = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        canonical = self._cmd_map.get(name, name)
        return canonical, args

    async def _dispatch_command(self, text: str) -> bool:
        """Retorna True para encerrar o terminal."""
        cmd, args = self._parse_command(text)

        if cmd == "exit":
            self.console.print("[yellow]Até logo![/yellow]")
            return True

        if cmd == "help":
            self._print_help()
            return False

        if cmd == "clear":
            self.engine.history.clear()
            self.console.print("[green]Histórico limpo.[/green]")
            return False

        if cmd == "history":
            await self._cmd_history()
            return False

        if cmd == "agents":
            await self._cmd_agents()
            return False

        if cmd == "model":
            await self._cmd_model(args)
            return False

        if cmd == "status":
            await self._cmd_status()
            return False

        if cmd == "query":
            await self._cmd_query(args)
            return False

        if cmd == "orchestrate":
            await self._cmd_orchestrate(args)
            return False

        self.console.print(f"[red]Comando desconhecido:[/red] /{cmd} — use /help")
        return False

    async def _cmd_history(self) -> None:
        turns = self.engine.history.list_turns()
        if not turns:
            self.console.print("[dim]Nenhum histórico nesta sessão.[/dim]")
            return
        table = Table(title="Histórico da sessão")
        table.add_column("#", justify="right")
        table.add_column("Você")
        table.add_column("Resposta")
        for i, t in enumerate(turns, 1):
            table.add_row(str(i), t.user[:50], t.assistant_summary[:60])
        self.console.print(table)

    async def _cmd_agents(self) -> None:
        status = self.engine.router.agent_status()
        table = Table(title="Agentes FIWARE")
        table.add_column("Agente")
        table.add_column("Status")
        for name, st in status.items():
            table.add_row(name, st)
        self.console.print(table)

    async def _cmd_model(self, args: str) -> None:
        if args:
            self.engine.slm.set_model(args)
            self.console.print(f"[green]Modelo SLM:[/green] {args}")
        else:
            self.console.print(f"Modelo atual: [bold]{self.engine.slm.current_model}[/bold]")

    async def _cmd_status(self) -> None:
        info = await self.engine.status()
        table = Table(title="Status DKRT")
        table.add_column("Serviço")
        table.add_column("Estado")
        table.add_column("Detalhe")
        ollama = info["ollama"]
        fiware = info["fiware"]
        table.add_row(
            "Ollama",
            "OK" if ollama.get("model_available") else "Atenção",
            f"{info['model']} @ {ollama.get('base_url')}",
        )
        table.add_row(
            "FIWARE Orion",
            "OK" if fiware.get("ok") else "Offline",
            fiware.get("url", "") if fiware.get("ok") else (fiware.get("error") or "")[:60],
        )
        self.console.print(table)

    async def _cmd_query(self, args: str) -> None:
        """Consulta NGSI direta sem passar pelo SLM."""
        parts = args.split() if args else []
        entity_type = parts[0] if parts else "Sensor"
        limit = int(parts[1]) if len(parts) > 1 else 20
        params = NgsiQueryParams(type=entity_type, limit=limit)

        self.console.print(f"[dim]GET /v2/entities type={entity_type} limit={limit}[/dim]")
        try:
            client = FiwareClient()
            entities = await client.query_entities(params)
            self.console.print(JSON(json.dumps(entities, ensure_ascii=False, indent=2)))
        except Exception as exc:
            self.console.print(
                f"[red]Orion indisponível.[/red] docker compose up -d\n{exc}"
            )

    async def _cmd_orchestrate(self, args: str) -> None:
        if not args:
            self.console.print("[yellow]Uso:[/yellow] /orchestrate consultar sensores")
            return
        orch = MultiAgentOrchestrator()
        result = await orch.orchestrate(args)
        table = Table(title=f"Orquestração — {result.status.value}")
        table.add_column("Agente")
        table.add_column("OK")
        table.add_column("Mensagem")
        for resp in result.responses:
            table.add_row(resp.agent_name, "OK" if resp.success else "FAIL", resp.message[:70])
        self.console.print(table)

    def _print_banner(self) -> None:
        self.console.print(
            Panel(
                "[bold]DKRT Terminal[/bold] — CLI externo\n"
                "Linguagem natural + comandos /query, /status, /agents\n"
                "Context Broker FIWARE Orion · SLM via Ollama",
                title="Bem-vindo",
                border_style="cyan",
            )
        )

    def _print_help(self) -> None:
        table = Table(title="Comandos do terminal DKRT")
        table.add_column("Comando")
        table.add_column("Descrição")
        for cmd in TERMINAL_COMMANDS:
            aliases = " ".join(cmd.aliases) if cmd.aliases else f"/{cmd.name}"
            table.add_row(aliases, cmd.help)
        table.add_row("(texto livre)", "Conversa ou pedido FIWARE via IA (SLM + agentes)")
        self.console.print(table)


def _configure_stdio() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _configure_logging() -> None:
    from context_broker_multiagent.core.chat_engine import configure_quiet_logging

    configure_quiet_logging()


def run() -> None:
    """Inicia o terminal DKRT (entry point principal)."""
    _configure_stdio()
    _configure_logging()
    terminal = DkrtTerminal()
    asyncio.run(terminal.run())


def main() -> None:
    """Alias para entry point setuptools."""
    run()
