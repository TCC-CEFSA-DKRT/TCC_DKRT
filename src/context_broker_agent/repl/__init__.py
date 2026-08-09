"""Modo REPL interativo (evita conflito com o módulo cli.py)."""

from context_broker_multiagent.repl.chat import register_chat_command

__all__ = ["register_chat_command"]
