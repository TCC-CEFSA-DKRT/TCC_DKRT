import pytest

from context_broker_multiagent.utils.ngsi_filters import (
    extract_lab_filter_from_text,
    normalize_entity_type,
    normalize_ngsi_q,
)


@pytest.mark.parametrize(
    "raw,user,expected",
    [
        (
            '?type=Sensor&where={"lab": "Lab 64"}',
            "lista sensores do lab 64",
            "lab==64",
        ),
        (None, "sensores do lab 64", "lab==64"),
        ("lab==64", "", "lab==64"),
        ("", "lab 64", "lab==64"),
    ],
)
def test_normalize_ngsi_q(raw, user, expected):
    assert normalize_ngsi_q(raw, user) == expected


def test_normalize_entity_type():
    assert normalize_entity_type("sensor") == "Sensor"
    assert normalize_entity_type("Device") == "Device"
