# 71 — Tema claro/escuro e interfaces do frontend

## 2026-11-15 — Revisão do Diego sobre a #61 (Tainara)

**Contexto:** na revisão da #61, o Diego pediu duas coisas: (1) no frontend, chamar de "interface" os arquivos de tipos (hoje `*.models.ts`), mantendo-os separados do código; (2) toda interface visual moderna deve ter pelo menos duas versões, escura e clara.

**O que mudou:**
- `shared/models/*.models.ts` virou `shared/interfaces/*.interface.ts`; `dashboard.models.ts` e `report-detail.models.ts` viraram `*.interface.ts`. Conteúdo igual, só o nome e os imports mudaram.
- Tipos que estavam dentro de componentes foram para arquivos próprios: `catalog.interface.ts`, `config.interface.ts`, `audit-runs.interface.ts`, `login.interface.ts`, `natural-language.interface.ts`, `status-badge.interface.ts` e `core/api-config.interface.ts`.
- `COMMAND_TEXT_MAX_LENGTH` saiu do arquivo de interfaces e foi para `natural-language.constants.ts` (é valor, não tipo).
- Tema claro: tokens em `styles.scss` (mixins `dark-theme` e `light-theme`), `ThemeService` (`core/theme.service.ts`) e o botão `ThemeToggleComponent` no menu lateral e nas telas de Login e Configuração.
- Cores fixas que estavam nas telas (`rgba(53, 240, 224, …)`, `rgba(5, 11, 17, …)`, `#b4fbf3`, `#eafffb`, `#23394a`) viraram tokens.
- `docs/design/design-system.md` ganhou a seção "Temas", com os contrastes do tema claro.

**Por quê / decisões:**
- O tema inicial segue o sistema operacional (`prefers-color-scheme`) e acompanha a mudança dele enquanto o usuário não escolher; depois da escolha, vale a escolha. O `styles.scss` também aplica o tema claro pela media query antes de o Angular iniciar, para não piscar o tema escuro em quem usa o sistema no modo claro.
- Cores com transparência usam um token só com o RGB (`--accent-rgb` etc.) dentro de `rgba(var(--accent-rgb), 0.1)`: assim cada tela mantém a sua transparência e só o tom muda com o tema. O tema escuro ficou idêntico ao da #61 (comparado pixel a pixel nas 7 telas, só o botão de tema é novo).
- `--text-glow-rgb` é branco no tema claro: o brilho dos títulos some sobre fundo claro sem precisar de regra separada em cada tela.
- No tema claro, "não conforme" usa `#C8336F` (vermelho puxado para magenta). Com vermelho puro, âmbar e vermelho ficavam com ΔE 3,1 para daltonismo deutan no validador de paleta; com `#C8336F` o par mais próximo é verde × âmbar, ΔE 7,3, a mesma situação do tema escuro (coberta por legenda, 2px entre segmentos e números escritos).
- O nome dos arquivos dos tipos de cada tela segue o da tela (`catalog.interface.ts`), igual a `dashboard.interface.ts`. Os tipos de API ficam em `shared/interfaces/`.

**Armadilhas e pontos de atenção:**
- `core/theme.service.ts::ThemeService` — é criado no início do app por `provideAppInitializer` (`app.config.ts`); sem isso, o atributo `data-theme` só seria aplicado quando alguma tela injetasse o serviço.
- `ThemeService.toggle` — o `localStorage` pode estar bloqueado (aba anônima, política do navegador). A troca de tema funciona mesmo assim; só não fica salva.
- `styles.scss` — o seletor `:root[data-theme='light']` ganha de `:root` por especificidade; a media query usa `:root:not([data-theme='dark'])` para não sobrescrever quem escolheu o escuro com o sistema no claro.
- `natural-language.interface.ts::ResultView` — qual painel mostrar depois da interpretação (issue #21): `ready` (pronto para revisar e confirmar, único com botão de confirmar), `clarify` (pedido ambíguo, com pergunta e sugestões), `discovery` (lista de tipos do broker), `out-of-scope` (pedido fora do domínio FIWARE, nada é executado), `unavailable` (o modelo de linguagem não respondeu).
- `natural-language.constants.ts::COMMAND_TEXT_MAX_LENGTH` — mesmo limite de `COMMAND_TEXT_MAX_LENGTH` do backend (`schemas.py`); se um mudar, o outro precisa mudar junto.
- `status-badge.interface.ts::BadgeKind` — junta os vocabulários `ConformanceStatus`, `RunStatus` e `ViolationSeverity` (`shared/interfaces/audit.interface.ts`), que usam o mesmo componente porque usam as mesmas cores.

**Referências:** issue #71, revisão do Diego na #61 (PRs #68 e #69), `docs/design/design-system.md`.
