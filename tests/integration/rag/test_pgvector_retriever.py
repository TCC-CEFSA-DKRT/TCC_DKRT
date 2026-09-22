"""Fase 6 — PgVectorRetriever. Ver .cursor/specs/fase6.spec.md, secoes 1.1
(contrato de KnowledgeRetrieverPort) e 6.1.

Requer Docker (Postgres com pgvector via testcontainers) e rede na primeira
execucao (baixa os pesos do embedder real). Nao roda no ambiente de sandbox
usado para desenvolver esta fase — rode localmente com:

    pip install -e ".[dev]"
    pytest -m integration tests/integration/rag/test_pgvector_retriever.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from auditor.application.use_cases.sync_knowledge_base import SyncKnowledgeBaseUseCase
from auditor.infrastructure.persistence.tables import create_all, knowledge_chunks_table
from auditor.infrastructure.rag.corpus_loader import CorpusLoader
from auditor.infrastructure.rag.embedder import SentenceTransformersEmbedder
from auditor.infrastructure.rag.pgvector_retriever import PgVectorRetriever

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture
async def engine(postgres_container):
    # module-scoped container, isolado por teste via TRUNCATE (ver
    # test_sync_knowledge_base.py — mesma disciplina).
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    eng = create_async_engine(async_url)
    await create_all(eng)
    async with eng.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE knowledge_chunks"))
    yield eng
    await eng.dispose()


@pytest.fixture(scope="module")
def embedder() -> SentenceTransformersEmbedder:
    return SentenceTransformersEmbedder()


async def _insert_fake_chunk(engine, *, chunk_id: str, embedding: list[float]) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            pg_insert(knowledge_chunks_table).values(
                chunk_id=chunk_id,
                category="convention",
                content=f"conteudo de {chunk_id}",
                tags=[],
                embedding=embedding,
                updated_at=datetime.now(timezone.utc),
            )
        )


class TestContract:
    """Fase 6, secao 1.1 — mesmos casos de teste de contrato do port,
    exercitados contra a implementacao real."""

    @pytest.mark.asyncio
    async def test_empty_corpus_returns_empty_list(self, engine, embedder):
        retriever = PgVectorRetriever(engine, embedder)

        results = await retriever.retrieve("qualquer query", top_k=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_more_relevant_chunks_than_top_k_returns_exactly_top_k_sorted_desc(
        self, engine, embedder
    ):
        [emb_a, emb_b, emb_c, emb_d] = await embedder.embed(["a", "b", "c", "d"])
        for chunk_id, emb in [
            ("chunk-a", emb_a),
            ("chunk-b", emb_b),
            ("chunk-c", emb_c),
            ("chunk-d", emb_d),
        ]:
            await _insert_fake_chunk(engine, chunk_id=chunk_id, embedding=emb)
        retriever = PgVectorRetriever(engine, embedder)

        results = await retriever.retrieve("a", top_k=3)

        assert len(results) == 3
        similarities = [r.similarity for r in results]
        assert similarities == sorted(similarities, reverse=True)

    @pytest.mark.asyncio
    async def test_top_k_larger_than_index_returns_all_without_duplicates(
        self, engine, embedder
    ):
        [emb_a, emb_b] = await embedder.embed(["a", "b"])
        await _insert_fake_chunk(engine, chunk_id="chunk-a", embedding=emb_a)
        await _insert_fake_chunk(engine, chunk_id="chunk-b", embedding=emb_b)
        retriever = PgVectorRetriever(engine, embedder)

        results = await retriever.retrieve("a", top_k=10)

        assert len(results) == 2
        assert len({r.chunk_id for r in results}) == 2

    @pytest.mark.asyncio
    async def test_equally_relevant_chunks_of_different_categories_both_appear(
        self, engine, embedder
    ):
        [emb] = await embedder.embed(["texto identico"])
        async with engine.begin() as conn:
            for chunk_id, category in [
                ("chunk-convention", "convention"),
                ("chunk-annotated", "annotated_case"),
            ]:
                await conn.execute(
                    pg_insert(knowledge_chunks_table).values(
                        chunk_id=chunk_id,
                        category=category,
                        content="mesmo texto",
                        tags=[],
                        embedding=emb,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
        retriever = PgVectorRetriever(engine, embedder)

        results = await retriever.retrieve("texto identico", top_k=5)

        categories_by_id = {r.chunk_id: r.category.value for r in results}
        assert categories_by_id["chunk-convention"] == "convention"
        assert categories_by_id["chunk-annotated"] == "annotated_case"


class TestRealCorpusRetrieval:
    """Fase 6, secao 6.1 — corpus curado real, ingerido via
    SyncKnowledgeBaseUseCase, e o criterio de pronto da fase tornado
    executavel."""

    @pytest.fixture
    async def ingested_engine(self, engine, embedder):
        use_case = SyncKnowledgeBaseUseCase(
            corpus_loader=CorpusLoader(), embedder=embedder, engine=engine
        )
        await use_case.execute()
        return engine

    @pytest.mark.asyncio
    async def test_lum_naming_query_surfaces_the_illuminance_synonym_chunk(
        self, ingested_engine, embedder
    ):
        retriever = PgVectorRetriever(ingested_engine, embedder)

        results = await retriever.retrieve(
            "atributo 'lum' fora do padrao de nomenclatura", top_k=3
        )

        result_ids = {r.chunk_id for r in results}
        assert "synonym-illuminance-level" in result_ids

    @pytest.mark.asyncio
    async def test_missing_timezone_query_surfaces_case_and_convention(
        self, ingested_engine, embedder
    ):
        retriever = PgVectorRetriever(ingested_engine, embedder)

        results = await retriever.retrieve("data sem horario nem fuso", top_k=5)

        result_ids = {r.chunk_id for r in results}
        assert "case-date-only-instead-of-full-iso8601" in result_ids
        assert "convention-datetime-iso8601-with-timezone" in result_ids
