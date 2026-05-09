from context_broker_multiagent.agents import MultiAgentOrchestrator


def test_orchestrator_classifies_context_broker_query() -> None:
    orchestrator = MultiAgentOrchestrator()

    response = orchestrator.handle("consultar sensores no Context Broker")

    assert response["status"] == "ok"
    assert response["results"][0]["agent"] == "QueryIntentAgent"
    assert "NGSI-v2" in response["results"][0]["message"]
