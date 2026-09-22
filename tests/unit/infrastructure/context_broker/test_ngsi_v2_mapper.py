"""Fase 4 — NgsiV2Mapper. Ver .cursor/specs/fase4.spec.md, secao 1.1."""

import pytest

from auditor.domain.errors import MalformedAttributeError
from auditor.infrastructure.context_broker.ngsi_v2_mapper import NgsiV2Mapper


@pytest.fixture
def mapper() -> NgsiV2Mapper:
    return NgsiV2Mapper()


class TestToPlainValues:
    def test_unwraps_a_simple_attribute(self, mapper):
        raw = {
            "id": "urn:ngsi-ld:Streetlight:001",
            "type": "Streetlight",
            "illuminanceLevel": {"type": "Number", "value": 0.8, "metadata": {}},
        }

        result = mapper.to_plain_values(raw)

        assert result["illuminanceLevel"] == 0.8

    def test_geojson_value_is_not_unwrapped_a_second_level(self, mapper):
        raw = {
            "id": "urn:ngsi-ld:Streetlight:001",
            "type": "Streetlight",
            "location": {
                "type": "geo:json",
                "value": {"type": "Point", "coordinates": [-3.7, 40.4]},
                "metadata": {},
            },
        }

        result = mapper.to_plain_values(raw)

        assert result["location"] == {"type": "Point", "coordinates": [-3.7, 40.4]}

    def test_id_and_type_are_preserved_as_is(self, mapper):
        raw = {"id": "urn:ngsi-ld:Streetlight:001", "type": "Streetlight"}

        result = mapper.to_plain_values(raw)

        assert result == {"id": "urn:ngsi-ld:Streetlight:001", "type": "Streetlight"}

    def test_metadata_is_dropped_from_the_plain_dict(self, mapper):
        raw = {
            "id": "urn:ngsi-ld:Streetlight:001",
            "type": "Streetlight",
            "dateCreated": {
                "type": "DateTime",
                "value": "2026-01-10T08:00:00Z",
                "metadata": {"timestamp": {"type": "DateTime", "value": "2026-01-10T08:00:01Z"}},
            },
        }

        result = mapper.to_plain_values(raw)

        assert result == {
            "id": "urn:ngsi-ld:Streetlight:001",
            "type": "Streetlight",
            "dateCreated": "2026-01-10T08:00:00Z",
        }

    def test_attribute_without_value_key_raises_malformed_attribute_error(self, mapper):
        raw = {
            "id": "urn:ngsi-ld:Streetlight:001",
            "type": "Streetlight",
            "illuminanceLevel": {"type": "Number"},  # falta "value"
        }

        with pytest.raises(MalformedAttributeError) as exc_info:
            mapper.to_plain_values(raw)

        assert exc_info.value.attribute_name == "illuminanceLevel"

    def test_attribute_that_is_not_a_dict_raises_malformed_attribute_error(self, mapper):
        raw = {
            "id": "urn:ngsi-ld:Streetlight:001",
            "type": "Streetlight",
            "illuminanceLevel": 0.8,  # sem envelope algum
        }

        with pytest.raises(MalformedAttributeError) as exc_info:
            mapper.to_plain_values(raw)

        assert exc_info.value.attribute_name == "illuminanceLevel"
