"""Valida conectividade real com todos os backends do docker-compose.

Roda depois de `docker compose up -d` e todos os serviços saudaveis.
Uso: python check_full_stack.py
"""
import asyncio

from context_broker_agent.services.fiware_client import FiwareClient
from context_broker_agent.services.quantumleap_client import QuantumLeapClient
from context_broker_agent.services.sth_comet_client import SthCometClient
from context_broker_agent.services.iot_agent_client import IoTAgentClient


async def main():
    checks = {
        "Orion (FIWARE)": FiwareClient().check_health(),
        "QuantumLeap": QuantumLeapClient().check_health(),
        "STH-Comet (se estiver rodando)": SthCometClient().check_health(),
        "IoT Agent MQTT": IoTAgentClient().check_health(),
    }
    for name, coro in checks.items():
        result = await coro
        status = "OK" if result.get("ok") else "FALHOU"
        print(f"[{status}] {name}: {result}")


if __name__ == "__main__":
    asyncio.run(main())