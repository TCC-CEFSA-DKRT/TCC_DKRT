"""build_orion_adapter — ver ADR-0023."""

from __future__ import annotations

import httpx

from auditor.infrastructure.context_broker.adapter_factory import build_orion_adapter
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter
from auditor.infrastructure.context_broker.orion_ld_adapter import OrionLdAdapter


def test_v2_builds_an_orion_adapter():
    client = httpx.AsyncClient()

    adapter = build_orion_adapter("v2", "http://orion:1026", client, api_key="k")

    assert isinstance(adapter, OrionAdapter)
    assert adapter._base_url_raw == "http://orion:1026"
    assert adapter._client is client
    assert adapter._api_key == "k"


def test_ld_builds_an_orion_ld_adapter():
    client = httpx.AsyncClient()

    adapter = build_orion_adapter("ld", "http://orion-ld:1026", client, api_key="k")

    assert isinstance(adapter, OrionLdAdapter)
    assert adapter._base_url_raw == "http://orion-ld:1026"
    assert adapter._client is client
    assert adapter._api_key == "k"


def test_unknown_version_falls_back_to_v2():
    adapter = build_orion_adapter("garbage", "http://orion:1026", httpx.AsyncClient())

    assert isinstance(adapter, OrionAdapter)
