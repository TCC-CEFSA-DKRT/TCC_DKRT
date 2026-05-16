import json
from pathlib import Path

import pytest

from context_broker_multiagent.services.rag_retrieve import RagRetriever


@pytest.fixture
def chunks_file(tmp_path):
    chunks = [
        {
            "chunk_id": "1",
            "small": "Listar entidades Sensor NGSI-v2",
            "big": "GET /v2/entities?type=Sensor",
            "metadata": {"category": "fiware", "source_file": "t.md"},
        },
        {
            "chunk_id": "2",
            "small": "Orquestrador multiagentes",
            "big": "MultiAgentOrchestrator asyncio.gather",
            "metadata": {"category": "multiagent", "source_file": "m.md"},
        },
    ]
    path = tmp_path / "chunks.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    return path


def test_rag_retrieve(chunks_file):
    retriever = RagRetriever(chunks_path=chunks_file)
    result = retriever.retrieve("consultar sensores no Orion", intent="query")
    assert "rewritten_queries" in result
    assert len(result["selected"]) <= 5
    assert result["selected"][0]["score"] >= 0


def test_rewrite_query():
    retriever = RagRetriever(chunks_path=Path("nonexistent.jsonl"))
    rw = retriever.rewrite_query("listar sensores")
    assert len(rw["rewritten_queries"]) >= 1
