from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.colors import Color


@dataclass(frozen=True)
class SeverityStyle:
    fill: Color
    text_hex: str
    border: Color
