#!/usr/bin/env python3
"""Chunking híbrido com Small2Big para base de conhecimento DKRT."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path

CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
HEADER = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
MAX_BIG = 2000
OVERLAP = 200


def protect_code_blocks(text: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        key = f"__CODE_{len(placeholders)}__"
        placeholders[key] = match.group(0)
        return key

    return CODE_FENCE.sub(repl, text), placeholders


def restore_code_blocks(text: str, placeholders: dict[str, str]) -> str:
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


def split_sections(md: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    matches = list(HEADER.finditer(md))
    if not matches:
        return [("", md.strip())]

    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        body = md[start:end].strip()
        if body:
            parts.append((title, body))
    return parts or [("", md.strip())]


def split_paragraphs(section: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", section) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 2 <= MAX_BIG:
            buf = f"{buf}\n\n{para}".strip() if buf else para
        else:
            if buf:
                chunks.append(buf)
            if len(para) > MAX_BIG:
                for i in range(0, len(para), MAX_BIG - OVERLAP):
                    chunks.append(para[i : i + MAX_BIG])
                buf = ""
            else:
                buf = para
    if buf:
        chunks.append(buf)
    return chunks


def make_small(big: str, section: str) -> str:
    first_line = big.split("\n", 1)[0][:120]
    if section:
        return f"{section}: {first_line}".strip()
    return first_line[:150]


def process_file(path: Path, category: str, version: str) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    protected, placeholders = protect_code_blocks(raw)
    records: list[dict] = []

    for section, body in split_sections(protected):
        for big_prot in split_paragraphs(body):
            big = restore_code_blocks(big_prot, placeholders)
            small = make_small(big, section)
            records.append(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "parent_id": f"{path.stem}::{section or 'root'}",
                    "small": small,
                    "big": big,
                    "metadata": {
                        "source_file": path.name,
                        "version": version,
                        "category": category,
                        "section": section or "root",
                        "language": "pt-BR",
                    },
                }
            )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunking híbrido DKRT")
    parser.add_argument("input", type=Path, help="Pasta ou arquivo Markdown")
    parser.add_argument("--out", type=Path, default=Path("knowledge/chunks"))
    parser.add_argument("--category", default="fiware")
    parser.add_argument("--version", default="2.0")
    args = parser.parse_args()

    files = [args.input] if args.input.is_file() else sorted(args.input.glob("**/*.md"))
    args.out.mkdir(parents=True, exist_ok=True)
    out_file = args.out / "chunks.jsonl"

    all_records: list[dict] = []
    for md_file in files:
        all_records.extend(process_file(md_file, args.category, args.version))

    with out_file.open("w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Gerados {len(all_records)} chunks em {out_file}")


if __name__ == "__main__":
    main()
