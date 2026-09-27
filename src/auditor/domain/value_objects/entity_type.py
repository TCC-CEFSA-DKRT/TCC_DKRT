"""EntityType value object — ver .cursor/specs/fase1.spec.md, secao 1.3."""

from dataclasses import dataclass

from auditor.domain.errors import InvalidEntityTypeError


@dataclass(frozen=True)
class EntityType:
    """Um tipo de entidade NGSI (ex.: "Streetlight").

    Nao normaliza capitalizacao de proposito: tipos NGSI sao case-sensitive,
    e normalizar silenciosamente esconderia um erro real do cliente.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidEntityTypeError("EntityType.value nao pode ser vazio.")
