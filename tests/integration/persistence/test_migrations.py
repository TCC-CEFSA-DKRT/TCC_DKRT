"""Fase 3 — migrations Alembic. Ver .cursor/specs/fase3.spec.md, secao 9.

Requer Docker (testcontainers sobe um Postgres pgvector/pgvector:pg16
descartavel — mesma imagem do docker-compose, ja que a migration inicial
executa `CREATE EXTENSION IF NOT EXISTS vector`). Nao roda no ambiente de
sandbox usado para desenvolver esta fase — rode localmente com:

    pip install -e ".[dev]"
    pytest -m integration tests/integration/persistence/test_migrations.py -v

NOTA: a migration inicial (migrations/versions/2f62abb9e945_initial_schema.py)
foi escrita a mao, sem `alembic revision --autogenerate` contra um banco real
(o ambiente de desenvolvimento nao tinha acesso a Docker) — este e' o teste
que efetivamente valida se ela funciona. Rode-o antes de confiar na migration
em qualquer ambiente real.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_TABLES = {
    "schema_cache",
    "audit_runs",
    "entity_reports",
    "violations",
    "recommendations",
    "knowledge_chunks",  # Fase 6
    "catalog_sync_status",  # Fase 8
    "tenant_accounts",
}


def _alembic_config(async_url: str) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    # env.py usa DATABASE_URL do ambiente com prioridade sobre alembic.ini.
    os.environ["DATABASE_URL"] = async_url
    return cfg


async def _table_names(async_url: str) -> set[str]:
    # Projeto e' 100% asyncpg (nunca psycopg2/psycopg) — a inspecao pos-
    # migration usa a mesma engine assincrona, via `run_sync`, em vez de
    # abrir uma engine sincrona que exigiria um driver que nao e' dependencia
    # do projeto.
    engine = create_async_engine(async_url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
    finally:
        await engine.dispose()


async def _column_names(async_url: str, table_name: str) -> set[str]:
    engine = create_async_engine(async_url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns(table_name)}
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


class TestUpgradeDowngrade:
    # Deliberadamente testes SINCRONOS (nao `async def`): `command.upgrade`/
    # `command.downgrade` chamam migrations/env.py, que roda
    # `asyncio.run(run_migrations_online())` internamente. Se o teste em si
    # ja fosse uma corrotina rodando dentro do event loop do pytest-asyncio,
    # esse `asyncio.run()` aninhado levantaria RuntimeError ("cannot be
    # called from a running event loop"). Por isso a parte assincrona
    # (`_table_names`) e' disparada aqui via `asyncio.run()` tambem, nunca
    # com `await` direto no corpo do teste.
    def test_upgrade_head_creates_all_tables(self, postgres_container):
        async_url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        cfg = _alembic_config(async_url)

        command.upgrade(cfg, "head")

        table_names = asyncio.run(_table_names(async_url))
        assert EXPECTED_TABLES.issubset(table_names)

        # limpa para o proximo teste do modulo partir de um banco vazio
        command.downgrade(cfg, "base")

    def test_downgrade_base_removes_all_tables(self, postgres_container):
        async_url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        cfg = _alembic_config(async_url)

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        table_names = asyncio.run(_table_names(async_url))
        assert EXPECTED_TABLES.isdisjoint(table_names)


class TestKnowledgeChunksSchema:
    # Fase 6 (.cursor/specs/fase6.spec.md, secao 5.1) — casos de teste
    # especificos da tabela knowledge_chunks, alem da presenca generica ja
    # coberta por TestUpgradeDowngrade acima.
    def test_embedding_column_is_vector_384_and_hnsw_cosine_index_exists(
        self, postgres_container
    ):
        async_url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        async def _inspect():
            engine = create_async_engine(async_url)
            try:
                async with engine.connect() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT format_type(atttypid, atttypmod) "
                                "FROM pg_attribute "
                                "WHERE attrelid = 'knowledge_chunks'::regclass "
                                "AND attname = 'embedding'"
                            )
                        )
                    ).scalar_one()
                    index_names = (
                        await conn.execute(
                            text(
                                "SELECT indexname FROM pg_indexes "
                                "WHERE tablename = 'knowledge_chunks'"
                            )
                        )
                    ).scalars().all()
                    using_hnsw = (
                        await conn.execute(
                            text(
                                "SELECT am.amname FROM pg_class idx "
                                "JOIN pg_am am ON idx.relam = am.oid "
                                "WHERE idx.relname = 'ix_knowledge_chunks_embedding_cosine'"
                            )
                        )
                    ).scalar_one()
                    return row, index_names, using_hnsw
            finally:
                await engine.dispose()

        column_type, index_names, index_method = asyncio.run(_inspect())

        assert column_type == "vector(384)"
        assert "ix_knowledge_chunks_embedding_cosine" in index_names
        assert index_method == "hnsw"

        command.downgrade(cfg, "base")

    def test_duplicate_chunk_id_insert_is_rejected_by_primary_key(
        self, postgres_container
    ):
        async_url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        async def _insert_twice():
            engine = create_async_engine(async_url)
            insert_stmt = text(
                "INSERT INTO knowledge_chunks "
                "(chunk_id, category, content, tags, embedding, updated_at) "
                "VALUES (:chunk_id, 'convention', 'texto', '[]', "
                ":embedding, now())"
            )
            embedding = "[" + ",".join("0" for _ in range(384)) + "]"
            try:
                async with engine.begin() as conn:
                    await conn.execute(
                        insert_stmt, {"chunk_id": "dup", "embedding": embedding}
                    )
                with pytest.raises(IntegrityError):
                    async with engine.begin() as conn:
                        await conn.execute(
                            insert_stmt, {"chunk_id": "dup", "embedding": embedding}
                        )
            finally:
                await engine.dispose()

        asyncio.run(_insert_twice())

        command.downgrade(cfg, "base")


class TestTenantAccountsSchema:
    def test_duplicate_login_email_is_rejected_by_unique_constraint(
        self, postgres_container
    ):
        async_url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        async def _insert_twice():
            engine = create_async_engine(async_url)
            insert_stmt = text(
                "INSERT INTO tenant_accounts "
                "(fiware_service, fiware_service_path, broker_url, login_email, "
                "password_hash) "
                "VALUES (:fiware_service, '/', 'https://orion.example.com', "
                "'dup@example.com', 'hash')"
            )
            try:
                async with engine.begin() as conn:
                    await conn.execute(insert_stmt, {"fiware_service": "tenant_a"})
                with pytest.raises(IntegrityError):
                    async with engine.begin() as conn:
                        await conn.execute(insert_stmt, {"fiware_service": "tenant_b"})
            finally:
                await engine.dispose()

        asyncio.run(_insert_twice())

        command.downgrade(cfg, "base")

    def test_login_email_without_password_hash_is_rejected(self, postgres_container):
        async_url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        async def _insert_incomplete_login():
            engine = create_async_engine(async_url)
            try:
                with pytest.raises(IntegrityError):
                    async with engine.begin() as conn:
                        await conn.execute(
                            text(
                                "INSERT INTO tenant_accounts "
                                "(fiware_service, fiware_service_path, broker_url, "
                                "login_email, password_hash) "
                                "VALUES ('tenant_c', '/', 'https://orion.example.com', "
                                "'sem-senha@example.com', NULL)"
                            )
                        )
            finally:
                await engine.dispose()

        asyncio.run(_insert_incomplete_login())

        command.downgrade(cfg, "base")

    def test_broker_api_key_column_is_renamed_to_encrypted(self, postgres_container):
        async_url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        columns = asyncio.run(_column_names(async_url, "tenant_accounts"))
        assert "broker_api_key_encrypted" in columns
        assert "broker_api_key" not in columns

        command.downgrade(cfg, "edfd0898f739")
        columns = asyncio.run(_column_names(async_url, "tenant_accounts"))
        assert "broker_api_key" in columns
        assert "broker_api_key_encrypted" not in columns

        command.downgrade(cfg, "base")
