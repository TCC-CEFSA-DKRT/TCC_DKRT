"""GET /catalog, GET /catalog/models, GET /catalog/models/{model_name}/schema.
Ver .cursor/specs/fase8.spec.md, secao 7, e o follow-up pos-Fase 8 que
adicionou os dois ultimos: a tela Catalog so mostrava o status agregado da
sincronizacao, sem lista navegavel dos modelos nem jeito de ver o conteudo
de cada um.

Global, nao por tenant (o catalogo de Smart Data Models nao e' um dado do
tenant) — unico router desta API sem `Depends(get_tenant)`.

ORDEM DE REGISTRO: `/models` e `/models/{model_name}/schema` sao
registrados DEPOIS de `""` (a rota-base `/catalog`) mas isso nao importa
aqui (ao contrario de audits.py) porque nenhum dos dois colide com um
path-param de outro -- `{model_name}` so aparece dentro de `/models/...`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auditor.domain.errors import SchemaUnavailableError
from auditor.infrastructure.config.container import (
    get_catalog_index,
    get_catalog_sync_status_repository,
    get_schema_catalog,
)
from auditor.infrastructure.schema_catalog.catalog_index import CatalogIndex
from auditor.infrastructure.schema_catalog.catalog_sync_status_repository import (
    CatalogSyncStatusRepository,
)
from auditor.infrastructure.schema_catalog.smart_data_models_adapter import SmartDataModelsAdapter
from auditor.interfaces.rest.schemas import (
    CatalogModelResponse,
    CatalogModelSchemaResponse,
    CatalogStatusResponse,
    PageResponse,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=CatalogStatusResponse)
async def get_catalog_status(
    repository: CatalogSyncStatusRepository = Depends(get_catalog_sync_status_repository),
) -> CatalogStatusResponse:
    status = await repository.get()
    if status is None:
        # Nunca sincronizado ainda — estado valido e explicito, nunca 404
        # (o catalogo em si existe e funciona via CatalogIndex.resolve(),
        # so' o HISTORICO de sincronizacao esta vazio).
        return CatalogStatusResponse(
            last_synced_at=None,
            last_sync_successful=None,
            last_sync_error=None,
            models_count=None,
        )
    return CatalogStatusResponse(
        last_synced_at=status.last_synced_at,
        last_sync_successful=status.last_sync_successful,
        last_sync_error=status.last_sync_error,
        models_count=status.models_count,
    )


@router.get("/models", response_model=PageResponse[CatalogModelResponse])
async def list_catalog_models(
    subject: str | None = None,
    q: str | None = Query(default=None, description="Filtro por substring em model_name (case-insensitive)."),
    page: int = 1,
    page_size: int = 50,
    catalog_index: CatalogIndex = Depends(get_catalog_index),
) -> PageResponse[CatalogModelResponse]:
    """Lista os modelos do catalogo empacotado (CatalogIndex.list_models(),
    sem rede -- a mesma fonte que `sync()` usa para computar
    `models_count`). Paginacao/filtro em memoria de proposito: o catalogo
    inteiro (~1000 modelos) cabe folgado em memoria, sem precisar de banco
    para isto -- ao contrario de GET /audits, que filtra no Postgres
    porque runs de auditoria SAO um dado do tenant, crescem sem limite e
    precisam ficar la mesmo."""
    entries = catalog_index.list_models()

    if subject:
        entries = [e for e in entries if e.subject == subject]
    if q:
        needle = q.lower()
        entries = [e for e in entries if needle in e.model_name.lower()]
    entries.sort(key=lambda e: (e.subject, e.model_name))

    total = len(entries)
    start = (page - 1) * page_size
    page_items = entries[start : start + page_size]
    has_next = start + page_size < total

    items = [
        CatalogModelResponse(subject=e.subject, model_name=e.model_name) for e in page_items
    ]
    return PageResponse(items=items, page=page, page_size=page_size, total=total, has_next=has_next)


@router.get("/models/{model_name}/schema", response_model=CatalogModelSchemaResponse)
async def get_catalog_model_schema(
    model_name: str,
    subject: str = Query(
        ...,
        description=(
            "Subject exato (ver GET /catalog/models) -- obrigatorio para "
            "desambiguar quando o mesmo model_name existe em mais de um "
            "subject (AmbiguousDataModelError, CatalogIndex.resolve())."
        ),
    ),
    catalog_index: CatalogIndex = Depends(get_catalog_index),
    schema_catalog: SmartDataModelsAdapter = Depends(get_schema_catalog),
) -> CatalogModelSchemaResponse:
    """Conteudo do schema de um modelo especifico -- busca ao vivo em
    raw.githubusercontent.com com o mesmo cache de 6 camadas (memoria ->
    Postgres -> ETag condicional) que a auditoria em si usa
    (SmartDataModelsAdapter.fetch_schema, Fase 2), nao uma busca paralela
    reimplementada aqui."""
    data_model = catalog_index.ref_for(subject, model_name)
    try:
        resolved = await schema_catalog.fetch_schema(data_model)
    except SchemaUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None

    return CatalogModelSchemaResponse(
        subject=subject,
        model_name=model_name,
        version=data_model.version,
        schema_url=data_model.schema_url,
        content=resolved.content,
        source=resolved.origin.source.value,
        fetched_at=resolved.origin.fetched_at,
    )
