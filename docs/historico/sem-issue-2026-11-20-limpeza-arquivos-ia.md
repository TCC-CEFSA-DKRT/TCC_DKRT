# Limpeza de arquivos de config de IA no repositório remoto

## 2026-11-20 — CLAUDE.md, AGENTS.md, .cursor/ e "Claude outputs/" saem do git (Diego)

**Contexto:** `.cursor/`, `CLAUDE.md`, `AGENTS.md` e uma pasta solta `Claude outputs/` estavam
todos versionados na raiz — pedido pra tirar isso do repositório remoto (continuam existindo
na máquina de quem já clonou, só deixam de ser rastreados a partir daqui).

**O que mudou:**
- `.gitignore` ganhou `/CLAUDE.md`, `/AGENTS.md`, `/.cursor/`, `/Claude outputs/`.
- `git rm --cached` nos quatro — os arquivos continuam no disco, só saem do índice do git (e,
  depois do push, do remoto).
- `docs/AGENTS.md` — cópia do `AGENTS.md` da raiz. É o único dos quatro com regra operacional
  de verdade (o que é proibido comentar, exceções, comando de verificação); sem uma cópia
  versionada, essa regra desaparecia do histórico do projeto pra quem não tivesse o arquivo
  local antigo.
- `docs/specs/` — cópia de `.cursor/specs/fase1.spec.md` a `fase10.spec.md`. Referenciado por
  mais de 130 arquivos de código (docstrings/comentários antigos, ex. `audit_run.py:1`) como
  "a spec de comportamento da fase" — não dava pra simplesmente apagar do remoto.
- `README.md` — a referência a `.cursor/specs/` virou `docs/specs/` (topo e seção "Estrutura
  do projeto").

**Por quê / decisões:**
- `CLAUDE.md` e `.cursor/rules/sem-comentarios.mdc` não ganharam cópia em `docs/`: os dois são
  só um ponteiro de 1-3 linhas pro `AGENTS.md` ("regras completas em AGENTS.md"), sem conteúdo
  próprio — copiar seria duplicar o `docs/AGENTS.md`.
- `Claude outputs/sem-issue-2026-11-20-ngsi-ld.md` não ganhou cópia: era uma versão antiga e
  incompleta do que já está em `docs/historico/sem-issue-2026-11-20-ngsi-ld.md` (`diff`
  confirmou que não tinha nada que o arquivo de histórico já não tivesse).
- Cópia em vez de mover + reescrever as 130+ referências a `.cursor/specs/` no código: o ganho
  de ter o caminho "oficial" em todo lugar não compensa o diff gigante só de comentário antigo
  mudando de texto; quem está com o `.cursor/` local continua lendo a referência original, quem
  não está (clone novo) acha o mesmo conteúdo em `docs/specs/` pelo README.

**Armadilhas e pontos de atenção:**
- Quem já tinha feito `git pull` antes desta mudança continua com os arquivos rastreados
  localmente até rodar a próxima sincronização; não é um problema, só não é instantâneo pra
  quem está no meio de outra branch.
- Este commit só tira os quatro itens da branch atual (`feat/ngsi-ld-config-selector`). Em
  `main` (e outras branches que não passarem por merge/cherry-pick desta mudança) os arquivos
  continuam versionados até alguém repetir o mesmo `git rm --cached` lá.

**Pendências:**
- Decidir se a mesma remoção deve ser replicada direto na `main` (fora do fluxo normal de PR)
  ou só chega lá quando este branch for mergeado.

**Referências:** `docs/AGENTS.md`, `docs/specs/README.md`.
