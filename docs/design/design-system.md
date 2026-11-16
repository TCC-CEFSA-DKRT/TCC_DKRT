# Design System — DKRT

Guia visual da interface do DKRT (issue #61). Substitui a versão da Fase 8 (tema claro,
uma família tipográfica, sem gradiente nem brilho): a identidade tem acento ciano/verde,
para que todas as telas tenham a mesma cara e a interface passe uma impressão profissional
na apresentação. O funcionamento das telas não muda.

Há dois temas, escuro e claro (seção "Temas" abaixo). As tabelas de paleta descrevem o
tema escuro; o claro troca só os valores, com os mesmos nomes de token.

Toda tela usa só os tokens de `frontend/src/styles.scss`. Cor, fonte ou espaçamento
"avulso" numa tela é bug de design.

## Tipografia

Fontes servidas pelo próprio app (pacotes `@fontsource`, registrados em `angular.json`):
nada é baixado do Google Fonts, então a interface funciona sem internet.

| Token | Família | Uso |
|---|---|---|
| `--font-display` | Chakra Petch 600/700 | Título da página, títulos de seção, botões primários, números de destaque |
| `--font-body` | IBM Plex Sans 400/500/600 | Corpo de texto, rótulos, tabelas |
| `--font-mono` | IBM Plex Mono 400/500 | Ids de entidade, atributos, valores encontrados/esperados, chips, JSON |

Escala (`rem`, base 16px): `0.75` (rótulo de coluna, badge) · `0.8125` (texto auxiliar)
· `0.875` (corpo denso) · `0.9375` (título de seção, em maiúsculas com espaçamento
`0.12em`) · `1.125` (título de cartão) · `2.25` (título da página).

## Paleta

Todos os pares de texto foram medidos (WCAG 2.1, contraste mínimo AA 4,5:1 para texto e
3:1 para bordas de controles).

| Token | Valor | Uso | Contraste |
|---|---|---|---|
| `--color-bg` | `#070B10` | Fundo da aplicação | — |
| `--color-bg-raised` | `#0B141D` | Painel lateral de Login e Configuração | — |
| `--color-surface` | `#0E1924` | Cartões e painéis (`.glass`) | — |
| `--color-surface-2` | `#13212E` | Campos, trilhos de gráfico | — |
| `--color-border` | `#1F3442` | Divisórias de tabela e cartões internos | decorativa |
| `--color-border-strong` | `#5A7A8C` | Borda de campos e botões secundários | 3,6:1 sobre `surface-2` |
| `--color-border-accent` | ciano a 28% | Borda dos cartões `.glass` | decorativa |
| `--color-text-primary` | `#E8F4F2` | Texto principal | 14,5:1 sobre `surface-2` |
| `--color-text-secondary` | `#9DB2BC` | Texto auxiliar, rótulos | 7,4:1 sobre `surface-2` |
| `--color-text-muted` | `#8399A5` | Dicas, rodapés | 5,5:1 sobre `surface-2` |
| `--color-accent` | `#35F0E0` | Marca (ciano): links, foco, títulos de seção, item ativo do menu | 11,4:1 |
| `--color-accent-2` | `#7DFF9A` | Segundo tom da marca (verde), usado no gradiente | — |
| `--gradient-accent` | `#2FE6D3 → #8CF36A` | Botão primário, logo, barras do ranking | texto `--color-on-accent` (`#04110F`) 12,3:1 |

Status e severidade (texto, badges, gráficos):

| Token | Valor | Uso | Contraste sobre `surface-2` |
|---|---|---|---|
| `--color-conformant` | `#4FD88A` | `conformant`, `completed` | 9,0:1 |
| `--color-partial` / `--color-warning` | `#F2B84B` | `partial`, severidade `WARNING` | 9,1:1 |
| `--color-non-conformant` | `#FF6B6B` | `non_conformant`, `failed`, severidade `ERROR` | 5,9:1 |
| `--color-no-model` | `#A3B1BB` | `no_model_found`, `queued` | 7,4:1 |
| `--color-schema-unavailable` | `#B896F5` | `schema_unavailable` | 6,8:1 |
| `--color-info` | `#6CB6FF` | severidade `INFO`, Nível 1 | 7,6:1 |

Nos gráficos, verde e âmbar ficam próximos para quem tem daltonismo protan: por isso todo
gráfico tem legenda com o nome de cada status, 2px de separação entre segmentos e os
números escritos ao lado. A cor nunca é a única forma de identificar um status.

## Temas

O usuário escolhe o tema no botão "Tema claro" / "Tema escuro" do menu lateral (e no canto
da tela de Login e Configuração). Sem escolha salva, o app segue o tema do sistema
operacional e acompanha se ele mudar. A escolha fica salva no navegador
(`localStorage`, chave `dkrt-theme`).

Como funciona: `ThemeService` (`core/theme.service.ts`) coloca `data-theme="dark"` ou
`data-theme="light"` no `<html>`. Em `styles.scss`, os valores de cada tema ficam nos
mixins `dark-theme` e `light-theme`; os nomes dos tokens são os mesmos nos dois, então
nenhuma tela precisa saber qual tema está ativo. Cores com transparência usam um token
RGB (`--accent-rgb`, `--accent-2-rgb`, `--inset-rgb`, `--text-glow-rgb`) com
`rgba(var(--accent-rgb), 0.1)`, para a transparência continuar igual nos dois temas.

Tema claro — contrastes medidos sobre `surface-2` (`#F1F5F7`):

| Token | Valor | Contraste |
|---|---|---|
| `--color-bg` | `#F3F6F8` | — |
| `--color-surface` | `#FFFFFF` | — |
| `--color-surface-2` | `#F1F5F7` | — |
| `--color-border-strong` | `#71858F` | 3,5:1 |
| `--color-text-primary` | `#0D1B24` | 16,0:1 |
| `--color-text-secondary` | `#3E5361` | 7,3:1 |
| `--color-text-muted` | `#566B77` | 5,1:1 |
| `--color-accent` | `#007A72` | 4,8:1 |
| `--color-conformant` | `#0F7F52` | 4,6:1 |
| `--color-partial` / `--color-warning` | `#9B6100` | 4,7:1 |
| `--color-non-conformant` | `#C8336F` | 4,6:1 |
| `--color-no-model` | `#5B6B75` | 5,0:1 |
| `--color-schema-unavailable` | `#6F42C1` | 5,9:1 |
| `--color-info` | `#1A63C2` | 5,3:1 |

O gradiente da marca e o texto escuro do botão primário são os mesmos nos dois temas
(12,3:1). No tema claro o vermelho de "não conforme" puxa para o magenta: com o vermelho
puro, âmbar e vermelho ficavam quase iguais para daltonismo deutan (ΔE 3,1). Com
`#C8336F`, o par mais próximo é verde × âmbar, ΔE 7,3 para protan, a mesma situação do
tema escuro, coberta pela legenda, pelos 2px entre segmentos e pelos números escritos.

Tons de cinza: o status nunca depende só da cor (badge com texto, legenda com nome,
números nos gráficos), então as telas continuam legíveis impressas em preto e branco ou
com o filtro de tons de cinza do sistema.

## Espaçamento, bordas e sombras

- Espaçamento em múltiplos de 4px: `--space-1` (4) · `--space-2` (8) · `--space-3` (12)
  · `--space-4` (16) · `--space-5` (20) · `--space-6` (24) · `--space-8` (32).
- Raios: `--radius-sm` (6px, campos e blocos internos) · `--radius-md` (10px, botões e
  cartões internos) · `--radius-lg` (14px, cartões `.glass`).
- Sombras: `--shadow-card` (cartões) e `--glow-accent` (brilho ciano do botão primário e
  do logo). O brilho é reservado para a marca e para a ação principal da tela.
- Foco do teclado: `--focus-ring`, anel ciano de 2px em todo elemento focável.

## Componentes globais (`styles.scss`)

| Classe | O que é |
|---|---|
| `.page-title`, `.page-subtitle` | Título e descrição de cada tela |
| `.section-title` | Título de seção em maiúsculas, ciano |
| `.glass` | Cartão escuro translúcido com borda ciano |
| `.btn-primary` | Ação principal (gradiente, texto escuro, maiúsculas) |
| `.btn-secondary` | Ação secundária (contorno, sem preenchimento) |
| `.chip` | Valor curto em fonte mono, contorno ciano |
| `.data-table` | Tabela com cabeçalho em maiúsculas e linha destacada no hover |
| `.legend`, `.swatch--*` | Legenda e amostras de cor de status dos gráficos |
| `.visually-hidden` | Texto só para leitor de tela |

Componentes compartilhados (`shared/components/`): `StatusBadgeComponent` (pílula com
borda na cor do status), `EmptyStateComponent`, `ErrorStateComponent`,
`LoadingSkeletonComponent`, `DiffViewComponent` e `SplitPanelComponent` (Login e
Configuração).

## Animação

- Transições de interface: 150ms `ease-out`.
- Com "reduzir movimento", todas as transições e animações do app são desligadas.

## Layout

- Menu lateral fixo de 250px; conteúdo com 32px de margem.
- Sem rolagem horizontal da página em 1366px (notebook) nem em 1920px (monitor grande):
  tabelas e o gráfico de evolução rolam dentro do próprio cartão quando precisam.

## Estados obrigatórios por tela

Toda tela tem estado **vazio** (explica por que não há dado e o que fazer), **carregando**
(skeleton) e **erro** (mensagem do que falhou e botão "Tentar novamente").
