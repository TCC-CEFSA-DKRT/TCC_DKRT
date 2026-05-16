#!/usr/bin/env python3
"""Cria entidades Sensor de exemplo no Orion."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from context_broker_multiagent.models.ngsi import NgsiEntity
from context_broker_multiagent.services.fiware_client import FiwareClient, FiwareError


async def main() -> None:
    client = FiwareClient()
    samples = [
        NgsiEntity(
            id=f"Sensor:{i:03d}",
            type="Sensor",
            attrs={"temperature": {"type": "Float", "value": 20.0 + i}},
        )
        for i in range(1, 4)
    ]
    for entity in samples:
        try:
            await client.create_entity(entity)
            print(f"Criado {entity.id}")
        except FiwareError as exc:
            if "already exists" in str(exc).lower() or "422" in str(exc):
                print(f"Já existe {entity.id}")
            else:
                raise


if __name__ == "__main__":
    asyncio.run(main())
