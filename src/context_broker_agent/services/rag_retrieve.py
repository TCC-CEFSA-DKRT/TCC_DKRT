"""Inferência RAG: rewrite, busca, HyDE simplificado e rerank."""

import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

from context_broker_agent.config import get_settings


class RagRetriever:
    """Recupera chunks da base de conhecimento local."""

    def __init__(self, chunks_path: Path | None = None) -> None:
        settings = get_settings()
        self.chunks_path = chunks_path or settings.knowledge_chunks_path
        self._chunks: list[dict[str, Any]] | None = None

    def load_chunks(self) -> list[dict[str, Any]]:
        if self._chunks is not None:
            return self._chunks
        chunks: list[dict[str, Any]] = []
        if self.chunks_path.exists():
            with self.chunks_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        chunks.append(json.loads(line))
        self._chunks = chunks
        return chunks

    def rewrite_query(self, query: str, intent: str = "query") -> dict[str, Any]:
        """Query rewriting por regras (Fase 8)."""
        lower = query.lower()
        rewrites = [query]

        if "sensor" in lower or "sensores" in lower:
            rewrites.append("GET /v2/entities type=Sensor NGSI-v2 Orion")
        if "entidade" in lower or "consultar" in lower or "listar" in lower:
            rewrites.append("query entities FIWARE Context Broker python aiohttp")
        if "subscription" in lower or "inscrever" in lower:
            rewrites.append("POST /v2/subscriptions NGSI-v2 notification")

        return {
            "original": query,
            "rewritten_queries": list(dict.fromkeys(rewrites)),
            "intent": intent,
        }

    def hyde_document(self, query: str) -> str:
        """Documento hipotético para busca (não incluir na resposta final)."""
        return (
            f"Documentação oficial NGSI-v2: para '{query}', use GET /v2/entities "
            "com cabeçalhos Fiware-Service e type=Sensor no Orion Context Broker."
        )

    @staticmethod
    def _score(query: str, chunk: dict[str, Any]) -> float:
        text = f"{chunk.get('small', '')} {chunk.get('big', '')}".lower()
        tokens = set(re.findall(r"\w+", query.lower()))
        if not tokens:
            return 0.0
        hits = sum(1 for t in tokens if t in text)
        return hits / math.sqrt(len(tokens))

    def search(self, query: str, *, top_k: int = 20, category: str | None = None) -> list[dict[str, Any]]:
        chunks = self.load_chunks()
        if category:
            chunks = [c for c in chunks if c.get("metadata", {}).get("category") == category]

        hyde = self.hyde_document(query)
        combined = f"{query} {hyde}"

        scored = [(self._score(combined, c), c) for c in chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def rerank(self, query: str, candidates: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
        """Rerank por relevância lexical."""
        ranked = []
        for chunk in candidates:
            score = self._score(query, chunk)
            ranked.append(
                {
                    "chunk_id": chunk.get("chunk_id", str(uuid.uuid4())),
                    "score": round(score, 4),
                    "reason": "overlap lexical + metadata",
                    "big": chunk.get("big", ""),
                    "metadata": chunk.get("metadata", {}),
                }
            )
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked[:top_n]

    def retrieve(self, query: str, intent: str = "query") -> dict[str, Any]:
        """Pipeline completo: rewrite → busca → rerank."""
        rewrite = self.rewrite_query(query, intent=intent)
        search_q = " ".join(rewrite["rewritten_queries"])
        candidates = self.search(search_q, top_k=20)
        selected = self.rerank(search_q, candidates, top_n=5)
        return {
            "rewritten_queries": rewrite["rewritten_queries"],
            "intent": intent,
            "candidates_count": len(candidates),
            "selected": selected,
        }
