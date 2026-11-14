# 61 — Melhoria do layout visual da interface

## 2026-11-14 — Nova identidade visual nas 7 telas (Tainara)

**Contexto:** a interface tinha o tema claro da Fase 8 e cada tela resolvia botões, cartões e tabelas do seu jeito. A issue #61 pede uma identidade visual única, a partir da prévia do Assistente aprovada pelo grupo (tema escuro, ciano/verde), sem mudar o funcionamento.

**O que mudou:**
- Guia visual em `docs/design/design-system.md` (substitui a versão da Fase 8), com os contrastes WCAG medidos.
- Tokens novos em `frontend/src/styles.scss` e componentes globais: `.glass`, `.btn-primary`, `.btn-secondary`, `.chip`, `.data-table`, `.legend`, `.swatch--*`, `.page-title`, `.page-subtitle`, `.section-title`, `.visually-hidden`.
- Fontes Chakra Petch, IBM Plex Sans e IBM Plex Mono servidas pelo próprio app (`@fontsource`, em `angular.json`); o link do Google Fonts saiu do `index.html`.
- Menu lateral, Login e Configuração (`SplitPanelComponent`), Painel, Auditorias, Assistente, Relatório e Catálogo no visual novo.
- Painel: cartões de resumo (auditorias, entidades auditadas, % conformes, entidades com violação), barra de status por tipo, ranking em barras e gráfico de evolução em colunas empilhadas, com a tabela dos números ao lado (`dashboard-charts.ts`).

**Por quê / decisões:**
- Fontes locais em vez do Google Fonts: a apresentação pode acontecer sem internet e o navegador não faz requisição externa.
- Os componentes visuais compartilhados ficaram em `styles.scss`, não em cada tela: o orçamento do Angular é de 4 kB de CSS por componente (`angular.json`, `anyComponentStyle`), e repetir botão, tabela e cartão em cada tela estourava esse limite.
- O escudo animado com circuitos da prévia do Assistente não entrou: o grupo decidiu deixar a tela sem esse elemento decorativo. O painel "Execução da auditoria" da prévia também não foi feito, porque seria funcionalidade nova; o fluxo do Assistente continua o mesmo.
- O ranking do Painel passou a dizer "entidades com violação": o número soma entidades não conformes e parciais (`dashboard-charts.ts::entitiesWithViolation`), e o texto antigo ("violações") sugeria contagem de violações.
- As cores de status nos gráficos vêm dos mesmos tokens dos badges. Verde e âmbar ficam próximos para daltonismo protan (diferença ΔE 7,0 no validador de paleta), por isso todo gráfico tem legenda, 2px entre segmentos e os números escritos.

**Armadilhas e pontos de atenção:**
- `natural-language.component.scss` — a tela do Assistente fica limitada a 960px de largura (`:host`), para o campo de comando não esticar demais em monitor grande.
- `layout/shell/shell.component.ts` — o conteúdo do menu fica num `.shell__nav-inner` com `position: sticky`; o `<nav>` em si ocupa a altura toda da página, para o fundo e a borda do menu não acabarem no meio de páginas longas.
- `dashboard-charts.ts::timelineColumns` — a altura de cada coluna é proporcional à maior auditoria da série; as colunas usam só conformes, parciais e não conformes (as entidades sem modelo não entram na evolução, como na lista anterior).
- `DashboardComponent.loadTimeSeries` — se a série de evolução falhar, só o gráfico fica vazio; o resto do Painel continua na tela.
- `layout/shell/shell.component.ts` — os ícones do menu são SVG inline com `currentColor` (sem biblioteca de ícones), herdados da issue #21.
- `DashboardComponent` — `categoryAggregates` e `typesRankedByViolations` continuam somando direto os campos de `RunSummary` (Fase 8, seção 3): nada é recontado no frontend.

**Pendências:**
- Validar o guia com o grupo antes do merge (critério de aceite da issue).
- O Relatório e o Catálogo não têm paginação/virtualização (ver `docs/historico/22-visualizacao-relatorio.md`).

**Referências:** issue #61, `docs/design/design-system.md`, PRs da #22 (#62/#63) e da #23 (#64/#65), dos quais esta branch depende.
