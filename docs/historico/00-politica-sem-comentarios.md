# 00 — Política de "sem comentários no código"

## 2026-11-08 — Criação da política e do diretório de histórico (Diego de Souza)

**Contexto:** o código vinha acumulando comentários explicativos. Medido em 2026-11-08 na árvore da `feat/22`: 683 comentários `#` e 308 docstrings em Python (184 arquivos de `src/`, `tests/` e `scripts/`) e 88 comentários em TypeScript (49 arquivos). A equipe decidiu concentrar esse contexto neste diretório.

**O que mudou:**
- Verificadores `scripts/ci/check_no_comments.py` e `scripts/ci/check_no_comments_frontend.js`: reprovam comentários em linhas adicionadas ou alteradas.
- Workflow `.github/workflows/ci-comentarios.yml` (PRs para `main`) e hook local `.githooks/pre-commit`.
- Regras para IA: `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/sem-comentarios.mdc`, `.github/copilot-instructions.md`.
- Testes do verificador Python em `tests/unit/scripts/test_check_no_comments.py`.

**Por quê / decisões:**
- Só linhas novas ou alteradas: proibir em tudo reprovaria o repositório inteiro. Mesma filosofia do `ruff (código alterado)` do CI de backend.
- Só comentários, não docstrings: FastAPI e Pydantic expõem docstrings no OpenAPI. Há a opção `--docstrings` no verificador Python, desligada por padrão.
- Diretivas de ferramenta (`# noqa`, `# type:`, `// eslint-…`, `// @ts-…`) liberadas: precisam estar no código.
- Escopo: `src/`, `tests/`, `scripts/` e `frontend/src/`. Terraform, workflows e Dockerfiles ficam fora.
- Workflow separado em vez de editar `ci-backend.yml` e `ci-frontend.yml`: ambos têm filtro de `paths` (uma mudança só em `scripts/` não os dispararia) e o de backend instala `torch`.

**Armadilhas e pontos de atenção:**
- `scripts/ci/check_no_comments_frontend.js::tsComments` — o scanner cru do TypeScript se perde depois de template string com `${}` e deixa passar comentários; por isso usa o parser e coleta os comentários de cada token.
- `scripts/ci/check_no_comments.py::added_lines` — o pathspec `src/**/*.py` do git exige subpasta e ignora arquivos direto em `scripts/`; por isso o diff usa `-- src tests scripts` e filtra por extensão.
- Renomear um arquivo sem alterar o conteúdo não é cobrado (`git diff -M`).
- `scripts/ci/check_no_comments_frontend.js::scssComments` — ignora `//` dentro de strings e de `url(...)`.

**Pendências:**
- Marcar "Comentários novos no código" como check obrigatório nas regras do GitHub (não é possível pelo repositório).
- Decidir se vale migrar os comentários antigos para o histórico; hoje eles não bloqueiam ninguém.
- Cada pessoa ativa o hook local uma vez por clone: `git config core.hooksPath .githooks`.

**Referências:** `AGENTS.md`, `docs/historico/README.md`.
