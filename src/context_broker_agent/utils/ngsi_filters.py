"""Normalização de filtros NGSI-v2 (parâmetro q) para Orion."""

from __future__ import annotations

import json
import re

# Caracteres permitidos em expressões q do Orion (NGSI-v2)
_NGSI_Q_RE = re.compile(r'^[\w.;=!<>"\'\s-]+$')

_ENTITY_TYPES = {
    "sensor": "Sensor",
    "sensors": "Sensor",
    "device": "Device",
    "devices": "Device",
}


def extract_lab_filter_from_text(text: str) -> str | None:
    """Extrai lab==N de frases como 'sensores do lab 64'."""
    lower = text.lower()
    if m := re.search(r"lab(?:orat[oó]rio)?\s*(\d+)", lower):
        return f"lab=={m.group(1)}"
    return None


def normalize_entity_type(entity_type: str | None) -> str | None:
    if not entity_type:
        return None
    key = entity_type.strip().lower()
    if key in _ENTITY_TYPES:
        return _ENTITY_TYPES[key]
    if entity_type[0].islower():
        return entity_type[0].upper() + entity_type[1:]
    return entity_type


def _repair_broken_q(raw: str, user_text: str) -> str | None:
    if "{" in raw:
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            obj = json.loads(raw[start:end])
            lab = obj.get("lab")
            if lab is not None:
                if isinstance(lab, str) and (m := re.search(r"(\d+)", lab)):
                    return f"lab=={m.group(1)}"
                if isinstance(lab, (int, float)):
                    return f"lab=={int(lab)}"
        except (json.JSONDecodeError, ValueError):
            pass

    if m := re.search(r'["\']?lab["\']?\s*[:=]\s*["\']?([^"\'&}]+)', raw, re.I):
        if digits := re.search(r"(\d+)", m.group(1)):
            return f"lab=={digits.group(1)}"

    return extract_lab_filter_from_text(user_text)


def normalize_ngsi_q(raw: str | None, user_text: str = "") -> str | None:
    """
    Converte saídas inválidas do SLM (JSON, query string HTTP) em q NGSI-v2 válido.
    Ex.: '?type=Sensor&where={"lab":"Lab 64"}' → 'lab==64'
    """
    if not raw or not str(raw).strip():
        return extract_lab_filter_from_text(user_text)

    q = str(raw).strip()
    broken = (
        q.startswith("?")
        or "where=" in q.lower()
        or "{" in q
        or "type=" in q.lower() and "==" not in q.split("type=")[0]
    )
    if broken:
        repaired = _repair_broken_q(q, user_text)
        if repaired:
            return repaired
        return extract_lab_filter_from_text(user_text)

    if not _NGSI_Q_RE.match(q):
        return extract_lab_filter_from_text(user_text)

    return q
