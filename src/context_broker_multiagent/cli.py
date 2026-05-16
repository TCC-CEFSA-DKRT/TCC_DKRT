"""CLI DKRT — Typer + Rich."""

import asyncio
import json
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from context_broker_multiagent.config import get_settings
from context_broker_multiagent.models.ngsi import NgsiQueryParams
from context_broker_multiagent.orchestrator import MultiAgentOrchestrator
from context_broker_multiagent.services.fiware_client import FiwareClient
from context_broker_multiagent.services.mcp_server import McpServer
from context_broker_multiagent.services.rag_retrieve import RagRetriever
from context_broker_multiagent.services.slm_service import SLMService

load_dotenv()
app = typer.Typer(name="dkrt", help="DKRT — Context Broker multiagent CLI")
console = Console()


def _run_async(coro):
    return asyncio.run(coro)


@app.command()
def query(
    entity_type: str = typer.Option("Sensor", "--type", "-t", help="Tipo NGSI"),
    entity_id: Optional[str] = typer.Option(None, "--id", help="ID da entidade"),
    limit: int = typer.Option(20, "--limit", "-l", help="Limite de resultados"),
) -> None:
    """Consulta entidades no Orion Context Broker."""
    params = NgsiQueryParams(type=entity_type, id=entity_id, limit=limit)

    async def _run():
        client = FiwareClient()
        return await client.query_entities(params)

    try:
        entities = _run_async(_run())
        console.print(JSON(json.dumps(entities, ensure_ascii=False, indent=2)))
    except Exception as exc:
        typer.secho(f"Erro: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc


@app.command()
def ask(
    text: str = typer.Argument(..., help="Pedido em linguagem natural"),
    rag: bool = typer.Option(False, "--rag", help="Recuperar contexto RAG antes"),
) -> None:
    """Interpreta NL, opcionalmente RAG, e orquestra agentes."""
    slm = SLMService()
    interpretation = slm.interpret_query(text)
    console.print(f"[bold]Interpretação[/bold] ({interpretation.source}): {interpretation.raw_interpretation}")

    metadata = {
        "intent": interpretation.intent,
        "ngsi_query": interpretation.ngsi_query.model_dump() if interpretation.ngsi_query else {},
        "entity": interpretation.entity.model_dump() if interpretation.entity else None,
    }

    if rag:
        retriever = RagRetriever()
        ctx = retriever.retrieve(text, intent=interpretation.intent)
        console.print(f"[dim]RAG: {len(ctx['selected'])} chunks selecionados[/dim]")
        metadata["rag_context"] = ctx

    async def _run():
        orch = MultiAgentOrchestrator()
        return await orch.orchestrate(text, metadata=metadata)

    result = _run_async(_run())
    _print_orchestration(result)


@app.command("orchestrate")
def orchestrate_cmd(
    query_text: str = typer.Argument(..., help="Texto para orquestração"),
) -> None:
    """Executa o orquestrador multiagentes explicitamente."""

    async def _run():
        orch = MultiAgentOrchestrator()
        return await orch.orchestrate(query_text)

    result = _run_async(_run())
    _print_orchestration(result)


@app.command("ollama-check")
def ollama_check() -> None:
    """Verifica conexão com Ollama e se o modelo Qwen está disponível."""
    slm = SLMService()

    async def _run():
        return await slm.check_ollama()

    try:
        info = _run_async(_run())
    except Exception as exc:
        typer.secho(f"Ollama inacessível: {exc}", fg=typer.colors.RED, err=True)
        typer.echo("Inicie com: ollama serve", err=True)
        raise typer.Exit(1) from exc

    table = Table(title="Ollama / Qwen2.5")
    table.add_column("Campo")
    table.add_column("Valor")
    table.add_row("URL", info["base_url"])
    table.add_row("Modelo configurado", info["configured_model"])
    table.add_row("Modelo disponível", "sim" if info["model_available"] else "NAO")
    table.add_row("Modelos instalados", ", ".join(info["installed_models"][:8]) or "(nenhum)")
    console.print(table)

    if not info["model_available"]:
        typer.secho(
            f"Ajuste OLLAMA_MODEL no .env (ex.: qwen2.5:7b). Rode: ollama list",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)


@app.command()
def agents() -> None:
    """Lista agentes registrados no orquestrador."""
    orch = MultiAgentOrchestrator()
    table = Table(title="Agentes DKRT")
    table.add_column("Nome")
    table.add_column("Timeout (s)")
    for agent in orch._agents:
        table.add_row(agent.name, str(agent.timeout_seconds))
    console.print(table)


@app.command()
def rag(
    query_text: str = typer.Argument(..., help="Consulta para RAG"),
    intent: str = typer.Option("query", "--intent", "-i"),
) -> None:
    """Inferência RAG (rewrite + busca + rerank)."""
    retriever = RagRetriever()
    result = retriever.retrieve(query_text, intent=intent)
    console.print(JSON(json.dumps(result, ensure_ascii=False, indent=2)))


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, "--host", "-h"),
    port: Optional[int] = typer.Option(None, "--port", "-p"),
) -> None:
    """Inicia servidor MCP HTTP."""

    async def _run():
        server = McpServer()
        settings = get_settings()
        await server.run(host=host or settings.mcp_server_host, port=port or settings.mcp_server_port)
        while True:
            await asyncio.sleep(3600)

    try:
        _run_async(_run())
    except KeyboardInterrupt:
        console.print("Servidor encerrado.")


def _print_orchestration(result) -> None:
    table = Table(title=f"Orquestração — status: {result.status.value}")
    table.add_column("Agente")
    table.add_column("OK")
    table.add_column("Mensagem")
    table.add_column("ms", justify="right")
    for resp in result.responses:
        table.add_row(
            resp.agent_name,
            "OK" if resp.success else "FAIL",
            resp.message[:80],
            f"{resp.elapsed_ms:.1f}",
        )
    console.print(table)
    console.print(JSON(json.dumps(result.aggregated_data, ensure_ascii=False, indent=2)))


from context_broker_multiagent.repl import register_chat_command

register_chat_command(app)


if __name__ == "__main__":
    app()
