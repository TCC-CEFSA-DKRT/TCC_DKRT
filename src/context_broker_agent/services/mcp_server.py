"""Servidor MCP HTTP com JSON-RPC 2.0."""

import json
from typing import Any

from aiohttp import web

from context_broker_agent.config import get_settings
from context_broker_agent.models.ngsi import NgsiQueryParams
from context_broker_agent.orchestrator import MultiAgentOrchestrator
from context_broker_agent.services.fiware_client import FiwareClient
from context_broker_agent.services.slm_service import SLMService

TOOLS: list[dict[str, Any]] = [
    {
        "name": "dkrt_orchestrate",
        "description": "Executa o orquestrador multiagentes DKRT",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "dkrt_query_entities",
        "description": "Consulta entidades NGSI-v2 no Orion",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "dkrt_interpret_nl",
        "description": "Interpreta linguagem natural (SLM/heurística)",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
]


class McpServer:
    """Servidor aiohttp para protocolo MCP simplificado."""

    def __init__(self) -> None:
        self._orchestrator = MultiAgentOrchestrator()
        self._fiware = FiwareClient()
        self._slm = SLMService()

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "tools": len(TOOLS)})

    async def mcp_handler(self, request: web.Request) -> web.Response:
        body = await request.json()
        method = body.get("method")
        req_id = body.get("id")
        params = body.get("params", {})

        if method == "tools/list":
            return web.json_response(
                {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}},
            )

        if method == "tools/call":
            result = await self._call_tool(params.get("name"), params.get("arguments", {}))
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)},
                        ],
                    },
                },
            )

        return web.json_response(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Método desconhecido: {method}"}},
        )

    async def _call_tool(self, name: str | None, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "dkrt_orchestrate":
            result = await self._orchestrator.orchestrate(arguments.get("query", ""))
            return result.model_dump()
        if name == "dkrt_query_entities":
            params = NgsiQueryParams(
                type=arguments.get("type", "Sensor"),
                limit=arguments.get("limit", 20),
            )
            entities = await self._fiware.query_entities(params)
            return {"entities": entities}
        if name == "dkrt_interpret_nl":
            interp = self._slm.interpret_query(arguments.get("text", ""))
            return interp.model_dump()
        return {"error": f"Ferramenta desconhecida: {name}"}

    def create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/health", self.health)
        app.router.add_post("/mcp", self.mcp_handler)
        return app

    async def run(self, host: str | None = None, port: int | None = None) -> None:
        settings = get_settings()
        host = host or settings.mcp_server_host
        port = port or settings.mcp_server_port
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        print(f"MCP DKRT em http://{host}:{port} (POST /mcp, GET /health)")
