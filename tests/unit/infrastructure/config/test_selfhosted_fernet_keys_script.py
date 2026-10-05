from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="script POSIX (sh)")

SCRIPT = Path(__file__).resolve().parents[4] / "selfhosted" / "fernet-keys.sh"


def _run(key_file: Path) -> str:
    env = dict(os.environ)
    env.pop("BROKER_API_KEY_ENCRYPTION_KEYS", None)
    env["BROKER_API_KEY_ENCRYPTION_KEYS_FILE"] = str(key_file)
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        [
            "sh",
            str(SCRIPT),
            sys.executable,
            "-c",
            "import os; print(os.environ['BROKER_API_KEY_ENCRYPTION_KEYS'])",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class TestFernetKeysScript:
    def test_generates_owner_only_valid_key_when_missing(self, tmp_path):
        key_file = tmp_path / "keys"

        stdout = _run(key_file)

        assert key_file.exists()
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
        Fernet(stdout)
        assert stdout == key_file.read_text().strip()

    def test_reuses_existing_key_across_runs(self, tmp_path):
        key_file = tmp_path / "keys"

        first = _run(key_file)
        second = _run(key_file)

        assert first == second

    def test_passes_rotation_list_through_unchanged(self, tmp_path):
        key_file = tmp_path / "keys"
        key_file.write_text("k2,k1\n")

        stdout = _run(key_file)

        assert stdout == "k2,k1"

    def test_regenerates_when_file_is_empty(self, tmp_path):
        key_file = tmp_path / "keys"
        key_file.write_text("")

        stdout = _run(key_file)

        Fernet(stdout)

    def test_leaves_no_tmp_file_behind(self, tmp_path):
        key_file = tmp_path / "keys"

        _run(key_file)

        assert list(tmp_path.glob("*.tmp")) == []
