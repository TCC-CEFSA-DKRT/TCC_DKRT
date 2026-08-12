import pytest
from aiohttp.test_utils import TestClient, TestServer

from context_broker_agent.services.mcp_server import McpServer


@pytest.mark.asyncio
async def test_health_and_tools_list():
    server = McpServer()
    app = server.create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"

        rpc = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert rpc.status == 200
        body = await rpc.json()
        assert "result" in body
        assert len(body["result"]["tools"]) >= 3
        names = {t["name"] for t in body["result"]["tools"]}
        assert "dkrt_orchestrate" in names
