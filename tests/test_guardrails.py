import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_detect_pii_clean(tmp_path):
    payload = {"intent": "query", "plan": ["x"], "files": [], "references": [], "guardrails": {}}
    f = tmp_path / "ok.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/rag/detect_pii.py"), "--file", str(f)],
        capture_output=True,
    )
    assert result.returncode == 0


def test_detect_pii_cpf(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text('{"cpf": "123.456.789-00"}', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/rag/detect_pii.py"), "--file", str(f)],
        capture_output=True,
    )
    assert result.returncode == 1


def test_validate_schema_valid(tmp_path):
    payload = {
        "intent": "query",
        "plan": ["passo 1"],
        "files": [],
        "references": [],
        "guardrails": {"pii_passed": True, "schema_passed": True},
    }
    f = tmp_path / "codegen.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/rag/validate_schema.py"), str(f)],
        capture_output=True,
    )
    assert result.returncode == 0
