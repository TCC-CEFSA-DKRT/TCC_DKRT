# Design System — FIWARE Conformance Auditor

Ver `.cursor/specs/fase8.spec.md`, seção 2. Referência para as cinco telas do frontend
(`docs/plano_refatoracao_v3.md`, seção 3.10) — "moderno e elegante, sem cara de IA":
ferramenta profissional de auditoria, não produto de consumo. Toda tela deve usar
exclusivamente os tokens abaixo; qualquer cor, fonte ou espaçamento "avulso" introduzido
ad hoc numa tela específica é bug de design, não escolha de implementação.

## Tipografia

Uma família só: **Inter** (via `@angular/material`-free `@fontsource` local ou CDN do
Google Fonts, carregada uma vez em `index.html`). Nunca uma segunda família decorativa —
títulos e corpo de texto usam a mesma família, diferenciados por peso e tamanho.

| Peso | Uso |
|---|---|
| 400 (Regular) | Corpo de texto, valores de tabela |
| 500 (Medium) | Labels, cabeçalhos de coluna, botões secundários |
| 600 (Semibold) | Títulos de seção, botões primários |
| 700 (Bold) | Título da página, números de destaque (ex.: contagem de violações) |

Escala de tamanho (`rem`, base 16px): `0.75` (caption/badge) · `0.875` (corpo denso,
padrão em tabelas) · `1` (corpo padrão) · `1.25` (título de card) · `1.5` (título de
seção) · `2` (título de página).

## Paleta

Identidade própria — nunca o roxo/azul de template de IA genérico. Base neutra fria
(slate) com um acento único de marca e cores semânticas fixas para status de
conformidade (reaproveitadas em toda a UI: badges, gráficos, bordas de card).

| Token | Valor (light) | Uso |
|---|---|---|
| `--color-bg` | `#F7F8FA` | Fundo da aplicação |
| `--color-surface` | `#FFFFFF` | Cards, tabelas, painéis |
| `--color-border` | `#E2E5EA` | Bordas, divisores |
| `--color-text-primary` | `#1A1D24` | Texto principal (contraste AA ≥ 7:1 sobre `--color-surface`) |
| `--color-text-secondary` | `#5B6270` | Texto auxiliar, labels (contraste AA ≥ 4.5:1) |
| `--color-accent` | `#0F6E5C` | Marca — verde petróleo, nunca roxo/azul genérico. Ações primárias, links, foco |
| `--color-accent-hover` | `#0B5647` | Hover/active de `--color-accent` |
| `--color-conformant` | `#1A7F4B` | Status `conformant` |
| `--color-partial` | `#B57A0A` | Status `partial` |
| `--color-non-conformant` | `#B23A3A` | Status `non_conformant`, severidade `ERROR` |
| `--color-no-model` | `#6B7280` | Status `no_model_found` |
| `--color-schema-unavailable` | `#8A6D9C` | Status `schema_unavailable` |
| `--color-warning` | `#B57A0A` | Severidade `WARNING` (mesmo tom de `partial` — mesma semântica) |
| `--color-info` | `#3B6FA0` | Severidade `INFO` |

Todas as cores de status/severidade têm par claro (fundo de badge, 10% de opacidade sobre
`--color-surface`) e escuro (texto/ícone do badge) — nunca só uma cor sólida preenchendo
uma área grande.

## Densidade

Alta, como ferramenta profissional (referência: Linear, Vercel, Datadog) — nunca
espaçamento de landing page numa tela de lista de 500 runs.

- Escala de espaçamento em múltiplos de 4px: `--space-1: 4px`, `--space-2: 8px`,
  `--space-3: 12px`, `--space-4: 16px`, `--space-6: 24px`, `--space-8: 32px`.
- Linha de tabela/lista: altura mínima 40px (`--space-8` + padding vertical `--space-2`),
  nunca 56px+ de padding "confortável" de app consumidor.
- Largura máxima de conteúdo: sem limite artificial em telas de tabela/lista (usam a
  largura disponível) — limite de `1280px` só em telas de formulário/detalhe de leitura
  longa (Report Detail, Natural Language).

## Ícones

Zero emoji como ícone de interface. Ícones de linha (stroke, não preenchidos), 16px ou
20px, de um único conjunto consistente (ex.: Lucide) — nunca misturar conjuntos.

## Decoração

Zero gradiente decorativo. Superfícies são sólidas (`--color-surface` sobre
`--color-bg`); a única variação visual permitida é a borda (`--color-border`) e sombra
sutil (`0 1px 2px rgba(16, 20, 24, 0.06)`) para elevar cards sobre o fundo — nunca sombra
colorida ou glow.

## Animação

Só onde comunica mudança de estado real — nunca só como enfeite.

- Transição de status (ex.: `running` → `completed` numa linha de Audit Runs): fade +
  leve highlight de fundo (`--color-accent` a 8% de opacidade, decaindo em 600ms).
- Progresso indeterminado (`total=null`, Fase 5): barra com animação de "carregando"
  contínua, nunca uma barra parada com percentual inventado.
- Toda outra transição de UI (abrir modal, trocar de aba): `150ms ease-out`, nunca mais
  que isso — instantâneo o suficiente para não parecer "devagar", suave o bastante para
  não parecer abrupto.

## Estados obrigatórios por tela

Todas as cinco telas (Dashboard, Audit Runs, Report Detail, Natural Language, Catalog)
implementam explicitamente:

1. **Vazio** — texto explicando por que não há dado (nunca um gráfico/tabela em branco
   sem explicação) e, quando aplicável, uma ação (ex.: "nenhum run ainda — inicie uma
   auditoria pela tela Natural Language").
2. **Carregando** — skeleton do layout real da tela (não um spinner genérico centralizado
   sem contexto do que está carregando).
3. **Erro** — mensagem explícita do que falhou, com botão "tentar novamente" — nunca uma
   tela em branco ou um carregando infinito.

## Componentes compartilhados (`shared/`)

Construídos uma vez, reusados pelas cinco features — nenhuma tela reimplementa badge de
status, estado vazio, estado de erro ou skeleton por conta própria:

- `StatusBadgeComponent` — mapeia `ConformanceStatus`/`RunStatus`/`ViolationSeverity` para
  cor + label, usando exclusivamente os tokens de paleta acima.
- `EmptyStateComponent`, `ErrorStateComponent`, `LoadingSkeletonComponent`.
- `DiffViewComponent` — usado no Report Detail para o diff "encontrado" vs. "esperado"/
  `proposed_patch`.
