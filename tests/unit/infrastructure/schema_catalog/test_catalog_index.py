"""Fase 2 — CatalogIndex. Ver .cursor/specs/fase2.spec.md, secao 2.

Os testes de `resolve()` usam a biblioteca `pysmartdatamodels` de verdade
(instalada como dependencia) — o catalogo vem empacotado com ela e nao
depende de rede, entao nao ha motivo para mockar aqui. Ja os casos de
ambiguidade e falha de sync usam um fake, porque nao sao reproduziveis com
dados reais do catalogo.
"""

import pytest

from auditor.domain.errors import AmbiguousDataModelError
from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.schema_catalog.catalog_index import (
    CatalogIndex,
    CatalogModelEntry,
    SyncResult,
)


class TestResolveWithRealLibrary:
    def test_known_type_resolves_to_data_model_ref(self):
        index = CatalogIndex()
        ref = index.resolve(EntityType("Streetlight"))

        assert ref is not None
        assert ref.subject == "dataModel.Streetlighting"
        assert ref.model_name == "Streetlight"
        assert ref.schema_url.endswith(
            "smart-data-models/dataModel.Streetlighting/master/Streetlight/schema.json"
        )

    def test_unknown_type_resolves_to_none_not_exception(self):
        index = CatalogIndex()
        assert index.resolve(EntityType("TipoQueNaoExiste123")) is None


class _FakeAmbiguousLibrary:
    """Simula um catalogo onde um datamodel aparece em dois subjects."""

    def subject_for_datamodel(self, datamodel: str):
        if datamodel == "Streetlight":
            return ["dataModel.Streetlighting", "dataModel.OutroDominio"]
        return False

    def update_data(self):
        raise NotImplementedError

    def list_all_subjects(self):
        raise NotImplementedError

    def datamodels_subject(self, subject: str):
        raise NotImplementedError


class TestResolveAmbiguity:
    def test_ambiguous_resolution_raises_instead_of_choosing_silently(self):
        index = CatalogIndex(library=_FakeAmbiguousLibrary())
        with pytest.raises(AmbiguousDataModelError):
            index.resolve(EntityType("Streetlight"))


class _FakeSyncLibrary:
    def __init__(self, *, update_ok: bool, subjects: dict[str, list[str]]):
        self._update_ok = update_ok
        self._subjects = subjects

    def subject_for_datamodel(self, datamodel: str):
        for subject, models in self._subjects.items():
            if datamodel in models:
                return [subject]
        return False

    def update_data(self):
        if not self._update_ok:
            raise ConnectionError("rede indisponivel")

    def list_all_subjects(self):
        return list(self._subjects.keys())

    def datamodels_subject(self, subject: str):
        return self._subjects[subject]


class TestSync:
    def test_successful_sync_reports_models_count(self):
        library = _FakeSyncLibrary(
            update_ok=True,
            subjects={"dataModel.Streetlighting": ["Streetlight", "StreetlightModel"]},
        )
        index = CatalogIndex(library=library)

        result = index.sync()

        assert result == SyncResult(success=True, models_count=2, reason=None)

    def test_sync_without_network_fails_but_reports_reason(self):
        library = _FakeSyncLibrary(update_ok=False, subjects={})
        index = CatalogIndex(library=library)

        result = index.sync()

        assert result.success is False
        assert result.models_count is None
        assert result.reason  # motivo registrado, nao silencioso

    def test_catalog_stays_usable_after_a_failed_sync(self):
        library = _FakeSyncLibrary(
            update_ok=False,
            subjects={"dataModel.Streetlighting": ["Streetlight"]},
        )
        index = CatalogIndex(library=library)

        sync_result = index.sync()
        assert sync_result.success is False

        # a falha de sync nao apaga o que ja existia — resolve() continua ok
        ref = index.resolve(EntityType("Streetlight"))
        assert ref is not None
        assert ref.subject == "dataModel.Streetlighting"


class TestListModels:
    def test_lists_every_subject_model_pair_from_the_library(self):
        library = _FakeSyncLibrary(
            update_ok=True,
            subjects={
                "dataModel.Streetlighting": ["Streetlight", "StreetlightModel"],
                "dataModel.Weather": ["WeatherObserved"],
            },
        )
        index = CatalogIndex(library=library)

        entries = index.list_models()

        assert set(entries) == {
            CatalogModelEntry(subject="dataModel.Streetlighting", model_name="Streetlight"),
            CatalogModelEntry(subject="dataModel.Streetlighting", model_name="StreetlightModel"),
            CatalogModelEntry(subject="dataModel.Weather", model_name="WeatherObserved"),
        }

    def test_never_needs_network_unlike_sync(self):
        # list_models() nao chama update_data() -- so' list_all_subjects()/
        # datamodels_subject(), a mesma leitura local que sync() usa para
        # computar models_count (ver docstring do modulo).
        library = _FakeSyncLibrary(
            update_ok=False,  # update_data() falharia, mas nunca e' chamado aqui
            subjects={"dataModel.Streetlighting": ["Streetlight"]},
        )
        index = CatalogIndex(library=library)

        entries = index.list_models()

        assert entries == [CatalogModelEntry(subject="dataModel.Streetlighting", model_name="Streetlight")]


class TestRefFor:
    def test_builds_a_valid_ref_without_consulting_the_library_at_all(self):
        # Ao contrario de resolve(), ref_for() nunca chama
        # subject_for_datamodel() -- por isso nunca pode levantar
        # AmbiguousDataModelError, mesmo que o library associado dissesse
        # o contrario (aqui simulado por uma library que sempre levanta se
        # chamada, para provar que ela nunca e' consultada).
        class _NeverCalledLibrary:
            def subject_for_datamodel(self, datamodel):
                raise AssertionError("ref_for() nao deveria consultar a library")

            def update_data(self):
                raise AssertionError

            def list_all_subjects(self):
                raise AssertionError

            def datamodels_subject(self, subject):
                raise AssertionError

        index = CatalogIndex(library=_NeverCalledLibrary())

        ref = index.ref_for("dataModel.Streetlighting", "Streetlight")

        assert ref.subject == "dataModel.Streetlighting"
        assert ref.model_name == "Streetlight"
        assert ref.version == "latest"
        assert ref.schema_url == (
            "https://raw.githubusercontent.com/smart-data-models/"
            "dataModel.Streetlighting/master/Streetlight/schema.json"
        )
