"""SmartDataModelsAdapter — implementa SchemaCatalogPort compondo
CatalogIndex, InMemorySchemaCache, SchemaCacheRepository e
ConditionalSchemaFetcher. Ver .cursor/specs/fase2.spec.md, secao 3.4, e
docs/plano_refatoracao_v3.md, Parte III, 3.3 (politica de 6 passos).

So depende do *Protocol* SchemaCacheRepository, nao da implementacao Postgres
— pode ser testado com um fake, sem banco real (o que a implementacao real
precisa de banco de verdade e' testado em isolado, secao 3.2).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from auditor.domain.entities.entity_report import SchemaOrigin, SchemaSource
from auditor.domain.errors import SchemaUnavailableError
from auditor.domain.ports.schema_catalog_port import ResolvedSchema, SchemaCatalogPort
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.schema_catalog.catalog_index import CatalogIndex
from auditor.infrastructure.schema_catalog.conditional_fetcher import (
    ConditionalSchemaFetcher,
    NewContent,
    NotModified,
    SchemaFetchUnavailableError,
)
from auditor.infrastructure.schema_catalog.in_memory_cache import InMemorySchemaCache
from auditor.infrastructure.schema_catalog.schema_cache_repository import SchemaCacheRepository


class SmartDataModelsAdapter(SchemaCatalogPort):
    def __init__(
        self,
        catalog_index: CatalogIndex,
        memory_cache: InMemorySchemaCache,
        cache_repository: SchemaCacheRepository,
        fetcher: ConditionalSchemaFetcher,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog_index = catalog_index
        self._memory_cache = memory_cache
        self._cache_repository = cache_repository
        self._fetcher = fetcher
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def resolve_data_model(self, entity_type: EntityType) -> DataModelRef | None:
        return self._catalog_index.resolve(entity_type)

    async def fetch_schema(self, data_model: DataModelRef) -> ResolvedSchema:
        entity_type = EntityType(data_model.model_name)

        # 1. memoria — se tem e ainda e recente, usa direto (nem banco nem rede)
        cached = self._memory_cache.get(entity_type)
        if cached is not None:
            return cached

        # 2. banco (fonte duravel, compartilhada entre workers)
        db_row = await self._cache_repository.get(entity_type)
        known_etag = db_row.etag if db_row is not None else None

        # 3. verificacao condicional (ETag) contra a fonte oficial
        try:
            fetch_result = await self._fetcher.fetch(data_model.schema_url, known_etag)
        except SchemaFetchUnavailableError:
            if db_row is not None:
                # 6. sem rede pra nem a checagem condicional, mas ha algo no
                # banco — usa mesmo assim, mas NUNCA como LIVE.
                resolved = ResolvedSchema(
                    data_model=data_model,
                    content=db_row.schema_content,
                    origin=SchemaOrigin(source=SchemaSource.CACHE, fetched_at=db_row.fetched_at),
                )
                self._memory_cache.set(entity_type, resolved)
                return resolved
            # 7. nada em nenhuma camada, sem rede — indisponivel de verdade
            raise SchemaUnavailableError(
                f"Schema para '{entity_type.value}' indisponivel: sem cache e sem rede."
            ) from None

        now = self._clock()

        if isinstance(fetch_result, NotModified):
            # 4. 304 — banco confirmado atual
            assert db_row is not None, (
                "NotModified so pode acontecer quando enviamos known_etag, "
                "que so existe se db_row nao era None"
            )
            await self._cache_repository.touch_last_checked(entity_type)
            resolved = ResolvedSchema(
                data_model=data_model,
                content=db_row.schema_content,
                origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=db_row.fetched_at),
            )
            self._memory_cache.set(entity_type, resolved)
            return resolved

        # 5. mudou (ou e a primeira busca, known_etag=None) — conteudo novo
        assert isinstance(fetch_result, NewContent)
        await self._cache_repository.save(
            entity_type=entity_type,
            data_model_name=data_model.model_name,
            content=fetch_result.content,
            etag=fetch_result.etag,
            fetched_at=now,
        )
        resolved = ResolvedSchema(
            data_model=data_model,
            content=fetch_result.content,
            origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=now),
        )
        self._memory_cache.set(entity_type, resolved)
        return resolved
