"""Tenant value object — ver .cursor/specs/fase1.spec.md, secao 1.2."""

from dataclasses import dataclass

from auditor.domain.errors import InvalidTenantError


@dataclass(frozen=True)
class Tenant:
    """Identidade multi-tenant do FIWARE: `Fiware-Service` + `Fiware-ServicePath`.

    Toda auditoria e escopada a exatamente um tenant. Isolamento nao e opcional
    (ver docs/plano_refatoracao_v3.md, Parte III, 3.8 - Seguranca).
    """

    fiware_service: str
    fiware_service_path: str = "/"

    def __post_init__(self) -> None:
        if not self.fiware_service:
            raise InvalidTenantError(
                "Tenant.fiware_service e obrigatorio e nao pode ser vazio."
            )
