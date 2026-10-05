"""Fase 1 — guarda de arquitetura. Ver .cursor/specs/fase1.spec.md, secao 5, e
docs/plano_refatoracao_v3.md, Parte II 2.1 / Parte VI 6.4: `domain/` nunca pode
importar nada alem da biblioteca padrao do Python. Este teste torna essa regra
verificavel por maquina, nao so por disciplina/revisao de codigo.
"""

import ast
import sys
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[3] / "src" / "auditor" / "domain"

_STDLIB_MODULE_NAMES = set(sys.stdlib_module_names) | {"__future__"}


def _top_level_module(dotted_name: str) -> str:
    return dotted_name.split(".")[0]


def _iter_python_files():
    return sorted(DOMAIN_ROOT.rglob("*.py"))


def _collect_imports(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(_top_level_module(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # import relativo dentro do proprio domain — sempre ok
            if node.module:
                modules.add(_top_level_module(node.module))
    return modules


def test_domain_root_exists():
    assert DOMAIN_ROOT.is_dir(), f"DOMAIN_ROOT nao encontrado em {DOMAIN_ROOT}"


def test_domain_has_no_dependencies_outside_stdlib_and_itself():
    offenders: dict[str, set[str]] = {}
    for path in _iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _collect_imports(tree):
            if module == "auditor":
                continue  # domain importando seus proprios submodulos e ok
            if module in _STDLIB_MODULE_NAMES:
                continue
            offenders.setdefault(str(path.relative_to(DOMAIN_ROOT)), set()).add(module)

    assert not offenders, (
        "domain/ so pode depender da biblioteca padrao do Python e de si mesmo. "
        f"Violacoes encontradas: {offenders}"
    )
