import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ci" / "check_no_comments.py"


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def run_check(cwd, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True
    )


def commit(repo, files, message="mudanca"):
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    commit(tmp_path, {"src/a.py": "x = 1  # antigo\n"}, "base")
    return tmp_path


def test_new_comment_is_reported_with_file_and_line(repo):
    commit(repo, {"src/a.py": "x = 1  # antigo\ny = 2  # novo\n"})

    result = run_check(repo, "--base", "HEAD~1")

    assert result.returncode == 1
    assert "src/a.py:2" in result.stdout
    assert "docs/historico" in result.stdout


def test_comment_that_was_already_there_is_not_reported(repo):
    commit(repo, {"src/a.py": "x = 1  # antigo\ny = 2\n"})

    result = run_check(repo, "--base", "HEAD~1")

    assert result.returncode == 0


def test_tool_directives_and_shebang_are_allowed(repo):
    commit(
        repo,
        {
            "scripts/run.py": "#!/usr/bin/env python3\na = 1  # noqa: E501\nb: int = 'x'  # type: ignore[assignment]\n"
        },
    )

    result = run_check(repo, "--base", "HEAD~1")

    assert result.returncode == 0


def test_hash_characters_inside_strings_are_not_comments(repo):
    commit(repo, {"src/a.py": "x = 1  # antigo\ncor = '#fff'\nurl = 'http://x.test/#ancora'\n"})

    result = run_check(repo, "--base", "HEAD~1")

    assert result.returncode == 0


def test_renaming_a_file_without_changing_it_is_not_reported(repo):
    git(repo, "mv", "src/a.py", "src/b.py")
    git(repo, "commit", "-qm", "renomeia")

    result = run_check(repo, "--base", "HEAD~1")

    assert result.returncode == 0


def test_docstring_is_only_reported_when_requested(repo):
    commit(repo, {"src/a.py": 'x = 1  # antigo\n\n\ndef f():\n    """explica"""\n    return 1\n'})

    default = run_check(repo, "--base", "HEAD~1")
    strict = run_check(repo, "--base", "HEAD~1", "--docstrings")

    assert default.returncode == 0
    assert strict.returncode == 1
    assert "docstring" in strict.stdout


def test_staged_mode_checks_the_index_before_commit(repo):
    (repo / "src" / "a.py").write_text("x = 1  # antigo\ny = 2  # novo\n", encoding="utf-8")
    git(repo, "add", "-A")

    result = run_check(repo, "--staged")

    assert result.returncode == 1
    assert "src/a.py:2" in result.stdout


def test_files_outside_the_checked_folders_are_ignored(repo):
    commit(repo, {"infra/main.py": "x = 1  # comentario\n"})

    result = run_check(repo, "--base", "HEAD~1")

    assert result.returncode == 0
