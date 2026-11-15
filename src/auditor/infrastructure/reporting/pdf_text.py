from __future__ import annotations

from xml.sax.saxutils import escape

from auditor.infrastructure.reporting.labels import RULE_LABELS
from auditor.infrastructure.reporting.pdf_theme import FIELD_MAX_CHARS

PDF_TEXT_ENCODING = "cp1252"


def clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]} … [truncado: {len(text)} caracteres no original]"


def pdf_safe(text: str) -> str:
    return text.encode(PDF_TEXT_ENCODING, errors="replace").decode(PDF_TEXT_ENCODING)


def safe_text(value: object, max_chars: int = FIELD_MAX_CHARS) -> str:
    text = "" if value is None else str(value)
    return escape(pdf_safe(clip_text(text, max_chars)))


def normalized_attribute_path(path: str) -> str:
    return path.strip().lower()


def rule_label(rule: str) -> str:
    known = RULE_LABELS.get(rule)
    if known:
        return known
    readable = " ".join(rule.replace("-", " ").replace("_", " ").split())
    return readable[:1].upper() + readable[1:] if readable else rule
