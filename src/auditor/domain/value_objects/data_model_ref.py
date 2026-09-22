"""DataModelRef value object — ver .cursor/specs/fase1.spec.md, secao 1.4."""

from dataclasses import dataclass, fields

from auditor.domain.errors import InvalidDataModelRefError


@dataclass(frozen=True)
class DataModelRef:
    """Referencia a um Smart Data Model — aponta para um schema, nao o conteudo.

    `subject` ex.: "dataModel.Streetlighting"; `model_name` ex.: "Streetlight".
    """

    subject: str
    model_name: str
    version: str
    schema_url: str

    def __post_init__(self) -> None:
        missing = [f.name for f in fields(self) if not getattr(self, f.name)]
        if missing:
            raise InvalidDataModelRefError(
                f"DataModelRef sem campo(s) obrigatorio(s): {', '.join(missing)}."
            )
