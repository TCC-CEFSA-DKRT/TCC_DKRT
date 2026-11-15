from __future__ import annotations


class ApplicationError(Exception):
    pass


class AuditReportTooLargeError(ApplicationError):
    def __init__(self, message: str, *, limit: int, actual: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.actual = actual

    @classmethod
    def too_many_entities(cls, *, limit: int, actual: int) -> AuditReportTooLargeError:
        return cls(
            f"Este relatório tem {actual} entidades e o limite para exportar em PDF é de "
            f"{limit}. Audite menos entidades por vez (por exemplo, um tipo de entidade "
            "por auditoria) e exporte novamente.",
            limit=limit,
            actual=actual,
        )

    @classmethod
    def document_too_big(cls, *, limit: int, actual: int) -> AuditReportTooLargeError:
        return cls(
            f"O PDF deste relatório ficou com {_kilobytes(actual)} KB e o limite para "
            f"exportação é de {_kilobytes(limit)} KB. Audite menos entidades por vez (por "
            "exemplo, um tipo de entidade por auditoria) e exporte novamente.",
            limit=limit,
            actual=actual,
        )


def _kilobytes(size: int) -> int:
    return round(size / 1000)
