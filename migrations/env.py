"""Alembic env.py — roda as migrations em modo assincrono (asyncpg), lendo a
URL de conexao de DATABASE_URL (mesma variavel de .env.example) em vez de
hardcoded em alembic.ini. Ver .cursor/specs/fase3.spec.md, secao 9.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Metadata combinado: schema_cache (Fase 2) + audit_runs/entity_reports/
# violations/recommendations (Fase 3) — uma unica migration inicial cobre
# o catalogo completo de tabelas do plano geral (Parte III, 3.7), como pede
# a secao 9 da spec da Fase 3.
from auditor.infrastructure.persistence.tables import metadata as persistence_metadata
from auditor.infrastructure.schema_catalog.postgres_schema_cache_repository import (
    metadata as schema_catalog_metadata,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = [persistence_metadata, schema_catalog_metadata]


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
