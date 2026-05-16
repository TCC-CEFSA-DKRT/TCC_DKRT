"""Registro de comandos do terminal DKRT."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerminalCommand:
    name: str
    help: str
    aliases: tuple[str, ...] = ()


TERMINAL_COMMANDS: list[TerminalCommand] = [
    TerminalCommand("help", "Lista comandos do terminal", ("/help", "/h", "?")),
    TerminalCommand("exit", "Encerra o terminal", ("/exit", "/quit", "/q")),
    TerminalCommand("clear", "Limpa histórico da sessão", ("/clear",)),
    TerminalCommand("history", "Mostra últimas mensagens", ("/history",)),
    TerminalCommand("status", "Ollama + FIWARE Orion", ("/status",)),
    TerminalCommand("agents", "Lista agentes FIWARE", ("/agents",)),
    TerminalCommand(
        "model",
        "Mostra ou altera modelo SLM (/model qwen2.5:3b)",
        ("/model",),
    ),
    TerminalCommand(
        "query",
        "Consulta direta NGSI (/query Sensor 20)",
        ("/query",),
    ),
    TerminalCommand(
        "orchestrate",
        "Orquestrador multiagentes (/orchestrate texto)",
        ("/orchestrate",),
    ),
]


def build_command_map() -> dict[str, str]:
    """Mapeia alias → nome canônico."""
    mapping: dict[str, str] = {}
    for cmd in TERMINAL_COMMANDS:
        mapping[cmd.name] = cmd.name
        for alias in cmd.aliases:
            mapping[alias.lstrip("/")] = cmd.name
            mapping[alias] = cmd.name
    return mapping
