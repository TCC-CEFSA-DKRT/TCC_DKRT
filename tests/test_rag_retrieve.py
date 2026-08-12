import json
from pathlib import Path

import pytest

from context_broker_agent.services.rag_retrieve import RagRetriever


@pytest.fixture
def chunks_file(tmp_path):
    chunk = {
        "chunk_id": "1",
        "small": "Listar entidades Sensor NGSI-v2",
        "big": "GET /v2/entities?type=Sensor",
        "metadata": {"category": "fiware", "source_file": "t.md"},
    }
    path = tmp_path / "chunks.jsonl"
    path.write_text(json.dumps(chunk) + "\n", encoding="utf-8")
    return path


def test_rag_pipeline(chunks_file):
    retriever = RagRetriever(chunks_path=chunks_file)
    result = retriever.retrieve("consultar sensores no broker", intent="query")
    assert "rewritten_queries" in result
    assert len(result["selected"]) >= 1


def test_rewrite_query():
    retriever = RagRetriever(chunks_path=Path("/nonexistent"))
    rw = retriever.rewrite_query("listar sensores")
    assert "listar sensores" in rw["rewritten_queries"]
