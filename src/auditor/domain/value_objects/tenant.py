"""Tenant value object — ver .cursor/specs/fase1.spec.md, secao 1.2."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    """Identidade multi-tenant do FIWARE: `Fiware-Service` + `Fiware-ServicePath`.

    `fiware_service == ""` e' valido: e' o servico default do Orion (sem
    isolamento multi-tenant), a mesma semantica do proprio NGSI-v2 -- um
    Orion self-hosted sem multi-tenancy nao usa `Fiware-Service`. A exigencia
    de tenant nao-vazio e' regra de aplicacao (fronteiras SaaS), nao do
    dominio; ver `interfaces/rest/access_tokens.py`.
    """

    fiware_service: str
    fiware_service_path: str = "/"
