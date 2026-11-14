from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExportedReport:
    content: bytes
    media_type: str
    filename: str


@dataclass(frozen=True)
class ReportExportLimits:
    max_entities: int
    max_bytes: int
