"""Fase 6 — SyncKnowledgeBaseUseCase. Ver .cursor/specs/fase6.spec.md,
secao 7.1.

Requer Docker (Postgres com pgvector via testcontainers) e rede na primeira
execucao (baixa os pesos do embedder real). Nao roda no ambiente de sandbox
usado para desenvolver esta fase — rode localmente com:

    pip install -e ".[dev]"
    pytest -m integration tests/integration/rag/test_sync_knowledge_base.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text
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
    # postgres_container e modulo-scoped (compartilhado entre testes deste
    # arquivo) -- trunca knowledge_chunks a cada teste para que cada um
    # comece de um banco vazio, independente da ordem de execucao.
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


async def _row_count(engine) -> int:
    async with engine.connect() as conn:
        rows = (await conn.execute(select(knowledge_chunks_table))).all()
    return len(rows)


class TestFirstSync:
    @pytest.mark.asyncio
    async def test_first_execute_against_empty_db_creates_the_whole_real_corpus(
        self, engine, embedder
    ):
        use_case = SyncKnowledgeBaseUseCase(
            corpus_loader=CorpusLoader(), embedder=embedder, engine=engine
        )
        expected_total = len(CorpusLoader().load_all())

        result = await use_case.execute()

        assert result.total == expected_total
        assert result.created == expected_total
        assert result.updated == 0
        assert result.deleted == 0
        assert await _row_count(engine) == expected_total

        # integra com o caso de teste da secao 6.1: apos a ingestao, uma
        # busca ja encontra resultados.
        retriever = PgVectorRetriever(engine, embedder)
        results = await retriever.retrieve(
            "atributo 'lum' fora do padrao de nomenclatura", top_k=3
        )
        assert len(results) > 0


class TestIdempotentResync:
    @pytest.mark.asyncio
    async def test_resync_without_changes_is_a_no_op(self, engine, embedder):
        use_case = SyncKnowledgeBaseUseCase(
            corpus_loader=CorpusLoader(), embedder=embedder, engine=engine
        )
        await use_case.execute()

        result = await use_case.execute()

        assert result.created == 0
        assert result.updated == 0
        assert result.deleted == 0


class TestCreatedUpdatedDeleted:
    @pytest.mark.asyncio
    async def test_new_entry_since_last_sync_is_created(self, engine, embedder, tmp_path):
        corpus_dir = _copy_real_corpus(tmp_path)
        loader = CorpusLoader()
        use_case = SyncKnowledgeBaseUseCase(
            corpus_loader=_FixedDirLoader(loader, corpus_dir), embedder=embedder, engine=engine
        )
        await use_case.execute()

        _append_convention(corpus_dir, chunk_id="convention-brand-new-entry", statement="novo")

        result = await use_case.execute()

        assert result.created == 1
        assert result.updated == 0
        assert result.deleted == 0

    @pytest.mark.asyncio
    async def test_changed_content_since_last_sync_is_updated_with_new_embedding(
        self, engine, embedder, tmp_path
    ):
        corpus_dir = _copy_real_corpus(tmp_path)
        loader = _FixedDirLoader(CorpusLoader(), corpus_dir)
        use_case = SyncKnowledgeBaseUseCase(corpus_loader=loader, embedder=embedder, engine=engine)
        await use_case.execute()

        _rewrite_first_convention_statement(corpus_dir, new_statement="texto totalmente revisado")

        result = await use_case.execute()

        assert result.updated == 1
        assert result.created == 0
        assert result.deleted == 0

    @pytest.mark.asyncio
    async def test_entry_removed_from_corpus_is_deleted_from_the_index(
        self, engine, embedder, tmp_path
    ):
        corpus_dir = _copy_real_corpus(tmp_path)
        loader = _FixedDirLoader(CorpusLoader(), corpus_dir)
        use_case = SyncKnowledgeBaseUseCase(corpus_loader=loader, embedder=embedder, engine=engine)
        await use_case.execute()

        _remove_first_convention(corpus_dir)

        result = await use_case.execute()

        assert result.deleted == 1
        assert result.created == 0
        assert result.updated == 0


class _FixedDirLoader:
    """Adaptador de teste: CorpusLoader real, mas sempre lendo de um
    corpus_dir fixo (copia isolada por teste do corpus real em tmp_path),
    para poder editar arquivos entre duas chamadas a execute() sem afetar
    knowledge/ real nem outros testes."""

    def __init__(self, loader: CorpusLoader, corpus_dir: Path) -> None:
        self._loader = loader
        self._corpus_dir = corpus_dir

    def load_all(self, corpus_dir: Path | None = None):
        return self._loader.load_all(corpus_dir or self._corpus_dir)


def _copy_real_corpus(tmp_path: Path) -> Path:
    import shutil

    from auditor.infrastructure.rag.corpus_loader import KNOWLEDGE_DIR

    corpus_dir = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, corpus_dir)
    return corpus_dir


def _append_convention(corpus_dir: Path, *, chunk_id: str, statement: str) -> None:
    path = corpus_dir / "conventions.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\n- id: {chunk_id}\n  statement: {statement}\n",
        encoding="utf-8",
    )


def _rewrite_first_convention_statement(corpus_dir: Path, *, new_statement: str) -> None:
    import yaml

    path = corpus_dir / "conventions.yaml"
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries[0]["statement"] = new_statement
    path.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")


def _remove_first_convention(corpus_dir: Path) -> None:
    import yaml

    path = corpus_dir / "conventions.yaml"
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries.pop(0)
    path.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
