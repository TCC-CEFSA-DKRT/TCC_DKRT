from unittest.mock import AsyncMock, patch

import pytest

from context_broker_multiagent.models.ngsi import NgsiEntity, NgsiQueryParams
from context_broker_multiagent.services.fiware_client import FiwareClient


@pytest.mark.asyncio
async def test_query_entities_mock():
    client = FiwareClient(base_url="http://test")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = [{"id": "Sensor:001", "type": "Sensor"}]
        entities = await client.query_entities(NgsiQueryParams(type="Sensor"))
    assert len(entities) == 1
    assert entities[0]["id"] == "Sensor:001"


def test_ngsi_entity_id_validation():
    with pytest.raises(ValueError):
        NgsiEntity(id="invalid", type="Sensor")
