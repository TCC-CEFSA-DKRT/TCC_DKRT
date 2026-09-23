"""SyncKnowledgeBaseUseCase — ver .cursor/specs/fase6.spec.md, secao 7.

Orquestra CorpusLoader -> to_chunk_text() -> Embedder.embed() (em lote) ->
upsert em knowledge_chunks por chunk_id -> remove do indice qualquer
chunk_id que nao exista mais no corpus atual. Analogo, em espirito, a um
"SyncCatalogUseCase" da Fase 2: mesma ideia de sincronizacao idempotente e
auditavel, aplicada ao corpus do RAG em vez do catalogo de modelos.

So' recalcula embedding para chunks novos ou cujo `content` mudou desde a
ultima sincronizacao (comparacao feita no banco, nao em memoria, para nao
depender de uma leitura previa completa da tabela) — condicao necessaria
para reindexacao repetida nao "custar" caro o tempo todo (fase6.spec.md,
secao 3, ultimo caso de teste de to_chunk_text: determinismo byte a byte).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from auditor.infrastructure.persistence.tables import knowledge_chunks_table
from auditor.infrastructure.rag.chunking import to_chunk_text
from auditor.infrastructure.rag.corpus_loader import CorpusLoader
from auditor.infrastructure.rag.embedder import Embedder


@dataclass(frozen=True)
class KnowledgeSyncResult:
    created: int
    updated: int
    deleted: int
    total: int


class SyncKnowledgeBaseUseCase:
    def __init__(
        self, corpus_loader: CorpusLoader, embedder: Embedder, engine: AsyncEngine
    ) -> None:
        self._corpus_loader = corpus_loader
        self._embedder = embedder
        self._engine = engine

    async def execute(self) -> KnowledgeSyncResult:
        entries = self._corpus_loader.load_all()
        chunk_texts = {entry.chunk_id: to_chunk_text(entry) for entry in entries}

        async with self._engine.connect() as conn:
            existing_rows = (
                await conn.execute(
                    select(
                        knowledge_chunks_table.c.chunk_id,
                        knowledge_chunks_table.c.content,
                    )
                )
            ).all()
        existing_content = {row.chunk_id: row.content for row in existing_rows}

        current_ids = set(chunk_texts)
        deleted_ids = set(existing_content) - current_ids

        to_upsert_ids = [
            chunk_id
            for chunk_id in current_ids
            if existing_content.get(chunk_id) != chunk_texts[chunk_id]
        ]
        created_count = sum(1 for cid in to_upsert_ids if cid not in existing_content)
        updated_count = len(to_upsert_ids) - created_count

        if to_upsert_ids:
            entries_by_id = {entry.chunk_id: entry for entry in entries}
            texts_to_embed = [chunk_texts[cid] for cid in to_upsert_ids]
            embeddings = await self._embedder.embed(texts_to_embed)
            now = datetime.now(timezone.utc)

            async with self._engine.begin() as conn:
                for chunk_id, embedding in zip(to_upsert_ids, embeddings):
                    entry = entries_by_id[chunk_id]
                    stmt = pg_insert(knowledge_chunks_table).values(
                        chunk_id=chunk_id,
                        category=entry.category.value,
                        content=chunk_texts[chunk_id],
                        tags=list(entry.tags),
                        embedding=embedding,
                        updated_at=now,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[knowledge_chunks_table.c.chunk_id],
                        set_={
                            "category": stmt.excluded.category,
                            "content": stmt.excluded.content,
                            "tags": stmt.excluded.tags,
                            "embedding": stmt.excluded.embedding,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await conn.execute(stmt)

        if deleted_ids:
            async with self._engine.begin() as conn:
                await conn.execute(
                    delete(knowledge_chunks_table).where(
                        knowledge_chunks_table.c.chunk_id.in_(deleted_ids)
                    )
                )

        return KnowledgeSyncResult(
            created=created_count,
            updated=updated_count,
            deleted=len(deleted_ids),
            total=len(current_ids),
        )
