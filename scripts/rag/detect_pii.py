#!/usr/bin/env python3
"""Detecção de PII em JSON de saída da IA."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.I)
API_KEY = re.compile(r"(api[_-]?key|secret|password)\s*[:=]\s*['\"]?\S+", re.I)
PLACEHOLDER_EMAILS = {"user@example.com", "test@example.com", "admin@example.com"}


def scan_text(text: str) -> list[str]:
    findings: list[str] = []
    if CPF.search(text):
        findings.append("CPF detectado")
    for match in EMAIL.finditer(text):
        if match.group(0).lower() not in PLACEHOLDER_EMAILS:
            findings.append(f"E-mail não placeholder: {match.group(0)}")
    if BEARER.search(text):
        findings.append("Bearer token detectado")
    if API_KEY.search(text):
        findings.append("Credencial hardcoded detectada")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    content = args.file.read_text(encoding="utf-8")
    findings = scan_text(content)

    for f in files_content_json(content):
        findings.extend(f)

    if findings:
        for item in findings:
            print(f"PII: {item}", file=sys.stderr)
        sys.exit(1)
    print("PII OK")
    sys.exit(0)


def files_content_json(raw: str) -> list[str]:
    extra: list[str] = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return extra
    for f in data.get("files", []):
        extra.extend(scan_text(f.get("content", "")))
    return extra


if __name__ == "__main__":
    main()
