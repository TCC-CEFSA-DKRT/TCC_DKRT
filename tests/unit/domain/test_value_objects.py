"""Fase 1 — Tenant, EntityType, DataModelRef. Ver .cursor/specs/fase1.spec.md, secao 1."""

import pytest

from auditor.domain.errors import (
    InvalidDataModelRefError,
    InvalidEntityTypeError,
    InvalidTenantError,
)
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant


class TestTenant:
    def test_empty_fiware_service_raises(self):
        with pytest.raises(InvalidTenantError):
            Tenant(fiware_service="")

    def test_default_service_path_is_root(self):
        tenant = Tenant(fiware_service="openiot")
        assert tenant.fiware_service_path == "/"

    def test_equal_tenants_compare_equal(self):
        assert Tenant("openiot", "/streetlights") == Tenant("openiot", "/streetlights")


class TestEntityType:
    def test_empty_value_raises(self):
        with pytest.raises(InvalidEntityTypeError):
            EntityType("")

    def test_preserves_case_exactly(self):
        assert EntityType("streetlight").value == "streetlight"
        assert EntityType("Streetlight").value == "Streetlight"


class TestDataModelRef:
    def test_valid_construction(self):
        ref = DataModelRef(
            subject="dataModel.Streetlighting",
            model_name="Streetlight",
            version="1.0.0",
            schema_url="https://smart-data-models.github.io/dataModel.Streetlighting/Streetlight/schema.json",
        )
        assert ref.model_name == "Streetlight"

    @pytest.mark.parametrize(
        "missing_field", ["subject", "model_name", "version", "schema_url"]
    )
    def test_missing_required_field_raises(self, missing_field):
        kwargs = {
            "subject": "dataModel.Streetlighting",
            "model_name": "Streetlight",
            "version": "1.0.0",
            "schema_url": "https://example.org/schema.json",
        }
        kwargs[missing_field] = ""
        with pytest.raises(InvalidDataModelRefError):
            DataModelRef(**kwargs)
