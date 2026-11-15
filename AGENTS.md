# Instruções para agentes de IA e colaboradores

Este arquivo é lido por assistentes de código (Cursor, Codex, Copilot, Claude Code etc.) e vale também para a equipe.

## Regra principal: nenhum comentário novo no código

Não escreva comentários em Python (`#`), TypeScript (`//`, `/* */`, `/** */`), HTML (`<!-- -->`) nem SCSS. O código deve se explicar por nomes claros, funções pequenas e testes.

Todo contexto que viraria comentário vai para o histórico de desenvolvimento: `docs/historico/<issue>-<slug>.md`.

- O que vai lá: por que algo foi feito assim, armadilhas encontradas, decisões pequenas, pendências, alternativas descartadas.
- Como apontar o código: `caminho/do/arquivo.py::funcao` (nunca número de linha).
- Sem issue: `sem-issue-AAAA-MM-DD-<slug>.md`.
- Decisão arquitetural duradoura continua em ADR (`docs/adr/`); especificação de fase em `.cursor/specs/`.
- Formato e modelo: `docs/historico/README.md`.

## O que pode ficar no código

- Diretivas de ferramenta: `# noqa`, `# type:`, `# pragma`, `# fmt:`, `# isort:`, `# pylint`, `# nosec`, `# nosemgrep`, `# mypy:`, `# pyright:`, `# ruff:`, shebang e linha de encoding; `// eslint-…`, `// @ts-…`, `/// <reference …>`, `// prettier-ignore`; `stylelint-…`.
- Docstrings não são barradas por esta regra (FastAPI e Pydantic usam docstrings na documentação da API), mas prefira não adicionar novas.
- Comentários que já existem no repositório podem ficar. A verificação olha só as linhas adicionadas ou alteradas no PR. Ao alterar uma linha que tem comentário, mova o conteúdo do comentário para o histórico.

## Como verificar antes de commitar

```
python scripts/ci/check_no_comments.py --base origin/main
node scripts/ci/check_no_comments_frontend.js --base origin/main
```

O verificador do frontend precisa de `npm ci` em `frontend/`.

Hook local, uma vez por clone: `git config core.hooksPath .githooks`. Ele roda as mesmas verificações sobre o que está no index.

O CI (workflow "CI Comentários") reprova o PR que adicionar comentário.

## Se você é uma IA

1. Antes de encerrar a tarefa, crie ou atualize a entrada da issue em `docs/historico/`.
2. Não contorne o verificador escondendo o comentário em string, docstring ou outro arquivo de código. Mova o conteúdo para `docs/historico/`.
3. Não apague comentários antigos que você não tocou nem reformate arquivos inteiros para "limpá-los": isso gera diff enorme e não é pedido.
