# Instruções para o Copilot

Não escreva comentários novos no código (Python, TypeScript, HTML, SCSS). Registre o contexto (por quê, armadilhas, decisões pequenas, pendências) em `docs/historico/<issue>-<slug>.md`, apontando o código por `caminho/arquivo.py::funcao`.

Diretivas de ferramenta (`# noqa`, `# type:`, `# pragma`, `// eslint-…`, `// @ts-…`) são permitidas. O CI reprova comentário novo.

Regras completas em `AGENTS.md`.
