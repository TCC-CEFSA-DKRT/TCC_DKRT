import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize

DIRECTIVE = re.compile(
    r"^#\s*(noqa|type:|pragma|fmt:|isort:|pylint|nosec|nosemgrep|mypy:|pyright:|ruff:|-\*-)",
    re.IGNORECASE,
)
ROOTS = ("src", "tests", "scripts")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
GUIDE = "Registre o contexto em docs/historico/<issue>.md (ver AGENTS.md) em vez de comentar no código."


def git(*args):
    return subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.quotepath=off", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def added_lines(base, head, staged):
    common = ["diff", "-M", "-U0", "--no-color", "--diff-filter=ACMR"]
    if staged:
        diff = git(*common, "--cached", "--", *ROOTS)
    else:
        diff = git(*common, f"{base}...{head}", "--", *ROOTS)
    result = {}
    current = None
    in_header = False
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            in_header = True
            current = None
        elif in_header and line.startswith("+++ "):
            name = line[4:].split("\t")[0]
            current = name[2:] if name.startswith("b/") and name.endswith(".py") else None
            if current is not None:
                result.setdefault(current, set())
        elif line.startswith("@@"):
            in_header = False
            match = HUNK.match(line)
            if match and current is not None:
                start = int(match.group(1))
                count = 1 if match.group(2) is None else int(match.group(2))
                result[current].update(range(start, start + count))
    return result


def source_of(path, head, staged):
    return git("show", f":{path}" if staged else f"{head}:{path}")


def comment_hits(path, source, lines, with_docstrings):
    hits = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT or token.start[0] not in lines:
                continue
            text = token.string.strip()
            if DIRECTIVE.match(text) or (token.start[0] == 1 and text.startswith("#!")):
                continue
            hits.append((token.start[0], "comentário", text))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        print(f"aviso: não foi possível analisar {path}", file=sys.stderr)
        return hits
    if with_docstrings:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return hits
        scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        for node in ast.walk(tree):
            if isinstance(node, scopes) and ast.get_docstring(node):
                first = node.body[0]
                if lines & set(range(first.lineno, first.end_lineno + 1)):
                    summary = ast.get_docstring(node)[:60].replace("\n", " ")
                    hits.append((first.lineno, "docstring", summary))
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reprova comentários novos em src, tests e scripts (só linhas adicionadas)."
    )
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--staged", action="store_true", help="verifica o que está no index (pre-commit)")
    parser.add_argument("--docstrings", action="store_true", help="também reprova docstrings novas")
    args = parser.parse_args(argv)

    files = added_lines(args.base, args.head, args.staged)
    total = 0
    for path in sorted(files):
        if not files[path]:
            continue
        try:
            source = source_of(path, args.head, args.staged)
        except subprocess.CalledProcessError:
            print(f"aviso: não foi possível ler {path}", file=sys.stderr)
            continue
        hits = comment_hits(path, source, files[path], args.docstrings)
        for line, kind, text in sorted(hits):
            print(f"{path}:{line}: {kind} novo -> {text[:70]}")
        total += len(hits)
    print(f"[python] {len(files)} arquivo(s) alterado(s); {total} comentário(s) novo(s)")
    if total:
        print(GUIDE)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
