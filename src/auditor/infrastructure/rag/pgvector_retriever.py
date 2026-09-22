"""PgVectorRetriever — implementa KnowledgeRetrieverPort via pgvector. Ver
.cursor/specs/fase6.spec.md, secao 6.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from auditor.domain.ports.knowledge_retriever_port import (
    KnowledgeCategory,
    RetrievedChunk,
)
from auditor.infrastructure.persistence.tables import knowledge_chunks_table
from auditor.infrastructure.rag.embedder import Embedder


class PgVectorRetriever:
    def __init__(self, engine: AsyncEngine, embedder: Embedder) -> None:
        self._engine = engine
        self._embedder = embedder

    async def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        [query_embedding] = await self._embedder.embed([query])

        cosine_distance = knowledge_chunks_table.c.embedding.cosine_distance(
            query_embedding
        )
        stmt = (
            select(
                knowledge_chunks_table.c.chunk_id,
                knowledge_chunks_table.c.category,
                knowledge_chunks_table.c.content,
                knowledge_chunks_table.c.tags,
                cosine_distance.label("distance"),
            )
            .order_by(cosine_distance)
            .limit(top_k)
        )

        async with self._engine.connect() as conn:
            result = await conn.execute(stmt)
            rows = result.mappings().all()

        return [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                category=KnowledgeCategory(row["category"]),
                content=row["content"],
                similarity=1.0 - float(row["distance"]),
                tags=tuple(row["tags"]),
            )
            for row in rows
        ]
