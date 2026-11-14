# Histórico de desenvolvimento

Aqui ficam os comentários que, em outros projetos, estariam espalhados pelo código. O código do DKRT não recebe comentários novos (regra em [`AGENTS.md`](../../AGENTS.md), verificada pelo CI): o contexto fica neste diretório, um arquivo por issue.

## Quando escrever

Ao fazer uma entrega (PR) ou ao tomar uma decisão pequena que o código sozinho não explica.

## Convenções

- Nome do arquivo: `<número da issue>-<slug>.md` (ex.: `22-visualizacao-relatorio.md`). Sem issue: `sem-issue-AAAA-MM-DD-<slug>.md`.
- Um arquivo por issue, para que várias pessoas em branches paralelas não gerem conflito de merge. Voltou à mesma issue? Acrescente uma entrada nova no topo do mesmo arquivo.
- Aponte o código por `caminho/arquivo.py::funcao` (ou `Componente.metodo`), nunca por número de linha: a linha muda, o nome não.
- Escreva o porquê, não o quê: o código já diz o que faz.

## Onde cada coisa vai

| Conteúdo | Lugar |
|---|---|
| Por que foi feito assim, armadilha, pendência, alternativa descartada | `docs/historico/` (aqui) |
| Decisão arquitetural duradoura, com alternativas e consequências | `docs/adr/` |
| Especificação de comportamento de uma fase | `.cursor/specs/` |
| O que o sistema faz e como usar | README e documentação técnica |

## Modelo de entrada

```
## AAAA-MM-DD — título curto (autor)

**Contexto:** o que motivou a mudança.

**O que mudou:** resumo do resultado.

**Por quê / decisões:** escolhas e alternativas descartadas.

**Armadilhas e pontos de atenção:**
- `caminho/arquivo.py::funcao` — o que não é óbvio ali.

**Pendências:** o que ficou para depois.

**Referências:** PR, issue, ADR.
```

## Verificação

O workflow "CI Comentários" reprova PRs que adicionam comentários em `src/`, `tests/`, `scripts/` e `frontend/src/`. O mesmo verificador roda localmente no pre-commit (`git config core.hooksPath .githooks`).
