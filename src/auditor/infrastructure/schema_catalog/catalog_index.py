"""CatalogIndex — resolucao entity_type -> DataModelRef via pysmartdatamodels.
Ver .cursor/specs/fase2.spec.md, secao 2.

O catalogo (lista de quais modelos existem) vem empacotado com a biblioteca
e nao depende de rede para `resolve()` — confirmado experimentalmente:
`pysmartdatamodels.pysmartdatamodels.subject_for_datamodel()` le um JSON local
(`model-assets/official_list_data_models.json`) instalado junto ao pacote.
So `sync()` (via `update_data()`) precisa de rede.

Decisao de design: `DataModelRef.schema_url` segue a convencao do proprio
catalogo Smart Data Models — `raw.githubusercontent.com/smart-data-models/
<subject>/master/<model_name>/schema.json` — confirmado por requisicao real
contra o schema do Streetlight (200 OK, com ETag). `version` nao vem do
catalogo de forma direta (nao ha uma API de release/versao estavel exposta
por `pysmartdatamodels`); como `schema_url` sempre aponta para a branch
`master` (rolling), o valor fixo "latest" e usado — o `$schemaVersion` real
(dentro do conteudo do schema) so fica disponivel depois de `fetch_schema()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from auditor.domain.errors import AmbiguousDataModelError
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType

_SCHEMA_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/smart-data-models/{subject}/master/"
    "{model_name}/schema.json"
)
_ROLLING_VERSION = "latest"


class SmartDataModelsLibrary(Protocol):
    """Subconjunto de `pysmartdatamodels.pysmartdatamodels` usado aqui —
    permite injetar um fake nos testes sem depender do pacote real."""

    def subject_for_datamodel(self, datamodel: str) -> "list[str] | bool": ...
    def update_data(self) -> Any: ...
    def list_all_subjects(self) -> "list[str]": ...
    def datamodels_subject(self, subject: str) -> "list[str]": ...


def _default_library() -> SmartDataModelsLibrary:
    from pysmartdatamodels import pysmartdatamodels as sdm_core

    return sdm_core


@dataclass(frozen=True)
class SyncResult:
    success: bool
    models_count: int | None
    reason: str | None = None


@dataclass(frozen=True)
class CatalogModelEntry:
    """Um (subject, model_name) do catalogo empacotado -- o par minimo que
    identifica um Smart Data Model sem ambiguidade (ao contrario de so'
    `model_name`, que pode existir em mais de um subject; ver
    AmbiguousDataModelError em resolve()). Usado por GET /catalog/models
    (Fase 8 follow-up: a tela Catalog so mostrava o status agregado da
    sincronizacao, sem lista navegavel nem conteudo de cada modelo)."""

    subject: str
    model_name: str


class CatalogIndex:
    """Resolve entity_type -> DataModelRef usando o catalogo empacotado."""

    def __init__(self, library: SmartDataModelsLibrary | None = None) -> None:
        self._library = library or _default_library()

    def resolve(self, entity_type: EntityType) -> DataModelRef | None:
        subjects = self._library.subject_for_datamodel(entity_type.value)
        if not subjects:
            return None
        if len(subjects) > 1:
            raise AmbiguousDataModelError(
                f"entity_type '{entity_type.value}' corresponde a mais de um "
                f"Smart Data Model subject: {list(subjects)}."
            )
        subject = subjects[0]
        schema_url = _SCHEMA_URL_TEMPLATE.format(subject=subject, model_name=entity_type.value)
        return DataModelRef(
            subject=subject,
            model_name=entity_type.value,
            version=_ROLLING_VERSION,
            schema_url=schema_url,
        )

    def sync(self) -> SyncResult:
        try:
            self._library.update_data()
        except Exception as exc:  # fronteira com biblioteca externa — tipo nao previsivel
            return SyncResult(success=False, models_count=None, reason=str(exc))

        try:
            models_count = sum(
                len(self._library.datamodels_subject(subject))
                for subject in self._library.list_all_subjects()
            )
        except Exception as exc:
            return SyncResult(
                success=True,
                models_count=None,
                reason=f"sync concluido, mas contagem de modelos falhou: {exc}",
            )
        return SyncResult(success=True, models_count=models_count, reason=None)

    def list_models(self) -> list[CatalogModelEntry]:
        """Todos os (subject, model_name) do catalogo empacotado -- mesma
        fonte usada por sync() para computar `models_count`
        (list_all_subjects + datamodels_subject), sem rede: a lista vem do
        JSON local, atualizado por sync() via update_data()."""
        return [
            CatalogModelEntry(subject=subject, model_name=model_name)
            for subject in self._library.list_all_subjects()
            for model_name in self._library.datamodels_subject(subject)
        ]

    def ref_for(self, subject: str, model_name: str) -> DataModelRef:
        """Constroi um DataModelRef diretamente a partir de um par
        (subject, model_name) ja' conhecido (ex.: vindo de list_models()),
        sem passar por resolve()/subject_for_datamodel() -- que pode
        levantar AmbiguousDataModelError quando o mesmo model_name existe
        em mais de um subject. GET /catalog/models/{model_name}/schema
        recebe o subject explicito na query string exatamente para evitar
        essa ambiguidade, entao construir o ref direto e' correto aqui."""
        schema_url = _SCHEMA_URL_TEMPLATE.format(subject=subject, model_name=model_name)
        return DataModelRef(
            subject=subject, model_name=model_name, version=_ROLLING_VERSION, schema_url=schema_url
        )
