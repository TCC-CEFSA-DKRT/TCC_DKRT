# Limpeza de arquivos de config de IA no repositório remoto

## 2026-11-20 — CLAUDE.md, AGENTS.md, .cursor/ e "Claude outputs/" saem do git (Diego)

**Contexto:** `.cursor/`, `CLAUDE.md`, `AGENTS.md` e uma pasta solta `Claude outputs/` estavam
todos versionados na raiz — pedido pra tirar isso do repositório remoto (continuam existindo
na máquina de quem já clonou, só deixam de ser rastreados a partir daqui). Aplicado direto em
`main` e `develop`, fora do fluxo normal de PR, a pedido.

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
- `README.md` — toda referência a `.cursor/specs/` virou `docs/specs/` (topo, seção
  "Experimento", seção "Débito conhecido" e seção "Estrutura do projeto").

**Por quê / decisões:**
- `CLAUDE.md` e `.cursor/rules/sem-comentarios.mdc` não ganharam cópia em `docs/`: os dois são
  só um ponteiro de 1-3 linhas pro `AGENTS.md` ("regras completas em AGENTS.md"), sem conteúdo
  próprio — copiar seria duplicar o `docs/AGENTS.md`.
- `Claude outputs/` (quando existia nesta branch) não ganhou cópia: era uma versão antiga e
  incompleta do que já está em `docs/historico/sem-issue-2026-11-20-ngsi-ld.md`.
- Cópia em vez de mover + reescrever as 130+ referências a `.cursor/specs/` no código: o ganho
  de ter o caminho "oficial" em todo lugar não compensa o diff gigante só de comentário antigo
  mudando de texto; quem está com o `.cursor/` local continua lendo a referência original, quem
  não está (clone novo) acha o mesmo conteúdo em `docs/specs/` pelo README.
- Referências a `.cursor/specs/` dentro de ADRs, `docs/historico/` e `docs/legacy/` não foram
  reescritas: são registro histórico do que era verdade na hora em que foram escritas, mesma
  lógica de não reescrever comentário antigo que ninguém tocou.

**Armadilhas e pontos de atenção:**
- Quem já tinha feito `git pull` antes desta mudança continua com os arquivos rastreados
  localmente até rodar a próxima sincronização; não é um problema, só não é instantâneo pra
  quem está no meio de outra branch.
- Commit direto em `main`/`develop`, sem PR — decisão explícita do autor, registrada aqui por
  não ser o fluxo padrão do projeto.

**Referências:** `docs/AGENTS.md`, `docs/specs/README.md`.
