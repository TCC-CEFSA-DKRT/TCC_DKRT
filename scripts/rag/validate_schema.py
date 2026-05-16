#!/usr/bin/env python3
"""Valida JSON de codegen contra schema DKRT."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None  # type: ignore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "schemas" / "codegen_output.schema.json",
    )
    args = parser.parse_args()

    data = json.loads(args.file.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))

    required = {"intent", "plan", "files", "references", "guardrails"}
    missing = required - set(data.keys())
    if missing:
        print(f"Campos ausentes: {missing}", file=sys.stderr)
        sys.exit(1)

    if Draft202012Validator is None:
        print("Instale jsonschema: pip install jsonschema", file=sys.stderr)
        sys.exit(1)

    if Draft202012Validator:
        validator = Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
        if errors:
            for err in errors:
                print(err.message, file=sys.stderr)
            sys.exit(1)

    print("Schema OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
