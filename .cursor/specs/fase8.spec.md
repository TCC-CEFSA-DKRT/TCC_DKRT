# Specs — Fase 8: Frontend Angular

Formato adaptado das fases anteriores: esta fase não é backend puro, então os "casos de
teste dado/quando/então" aqui descrevem cenários de tela (E2E/Cypress-ou-Playwright,
componente por componente), não contratos de `Protocol` Python. As cinco telas vêm da
seção 3.10 do plano geral; a estrutura por feature, do mesmo lugar.

**Angular, nunca React, sem exceção (plano geral, seção 1.3).**

---

## 0. Pré-requisito: endpoints REST que ainda não existem

A árvore de diretórios do plano geral (seção 2.2) já reserva
`interfaces/rest/routers/{reports.py, catalog.py}` — hoje só `audits.py`/`health.py`
existem (Fases 4–5). Esta fase precisa, **antes** das telas, de três adições de backend
(reaproveitando ports/use cases já existentes — nenhum conceito novo de domínio):

### 0.1 `GET /audits` — lista com filtros (tela "Audit Runs")

```python
# interfaces/rest/routers/reports.py (ou estendendo audits.py — a decidir na implementação)
@router.get("", response_model=Page[AuditRunSummaryResponse])
async def list_audits(
    tenant: Tenant = Depends(get_tenant),
    entity_type: str | None = None, status: str | None = None,
    started_after: datetime | None = None, started_before: datetime | None = None,
    page: int = 1, page_size: int = 20,
) -> Page[AuditRunSummaryResponse]: ...
```

Reaproveita `AuditRepositoryPort.list_runs`/`RunFilters`/`Page` (já implementados e
testados na Fase 3) — este endpoint é só a borda HTTP que faltava, sem lógica nova.

**Casos de teste (mesmo padrão da Fase 4, `ASGITransport` + fakes):**
- Dado `status=non_conformant` na query string, quando `GET /audits?status=non_conformant`
  é chamado, então `RunFilters.status` é passado corretamente ao repositório.
- Dado um tenant sem nenhum run, quando chamado, então retorna `Page(items=[], total=0)`,
  não 404 — lista vazia é resultado válido, distinto de recurso inexistente (mesmo
  princípio já usado em `GET /audits/{id}`, Fase 4).

### 0.2 `GET /audits/summary-over-time` — dados do Dashboard

Reaproveita `AuditRepositoryPort.list_run_summaries_over_time` (Fase 3, já implementado,
nunca exposto via HTTP). Recebe `entity_type` obrigatório (a agregação é por tipo, ver
seção 2 abaixo).

### 0.3 `POST /audits/interpret` — tradução de linguagem natural (tela "Natural Language")

Novo, pequeno: reaproveita `SemanticAnalyzerPort`/`OllamaAnalyzer` (Fase 7) com um prompt
diferente — não analisa entidade, traduz um comando em texto livre para os parâmetros de
`POST /audits`. **Nunca executa a auditoria sozinho** — devolve a interpretação para
confirmação humana (seção 6).

```python
class InterpretAuditCommandUseCase:
    async def execute(self, tenant: Tenant, command_text: str) -> AuditCommandInterpretation: ...

@dataclass(frozen=True)
class AuditCommandInterpretation:
    entity_type: str | None
    entity_id: str | None
    confidence: float
    raw_command: str
```

**Casos de teste:**
- Dado `"audite os sensores de qualidade do ar"`, quando `execute()` é chamado, então
  `entity_type` reflete um tipo NGSI plausível (ex.: `"AirQualityObserved"`) — testado com
  `httpx.MockTransport` no adaptador subjacente, mesmo padrão da Fase 7, seção 5.1.
- Dado um comando ambíguo ou sem tipo de entidade identificável, quando `execute()` é
  chamado, então `entity_type=None` e `confidence` baixo — a tela precisa distinguir "não
  entendi" de "entendi algo", nunca inventar um tipo plausível-mas-errado.
- **Nunca** chama `RunAuditUseCase.start()` — este use case só interpreta, não audita;
  quem decide confirmar e disparar a auditoria de verdade é a interação do usuário na tela
  (seção 6), nunca o backend sozinho.

---

## 1. Arquitetura do frontend (plano geral, seção 3.10)

- Angular (versão LTS mais recente no momento da implementação), **standalone components**
  (sem `NgModule`), roteamento lazy por feature.
- Estado local com **signals** — sem NgRx/store global: o estado de auditoria já vive no
  backend (polling/SSE, Fase 5), o frontend não precisa duplicar isso numa store própria.
- Um `ApiService` por feature, tipado com as mesmas formas de `interfaces/rest/schemas.py`
  (backend) — os DTOs TypeScript espelham `AuditRunResponse`, `AuditProgressResponse`,
  `EntityReportResponse` etc. campo a campo; qualquer divergência de nome/tipo é bug de
  contrato, não estilo.
- Estrutura de diretórios: exatamente a árvore da seção 2.2 do plano geral
  (`core/`, `shared/`, `features/{dashboard,audit-runs,report-detail,natural-language}/`,
  `layout/`) — acrescida de `features/catalog/` para a quinta tela (seção 5 abaixo), que a
  árvore original deixou implícita em "Catalog" na lista de telas sem refletir no diretório.

---

## 2. Design system — "moderno e elegante, sem cara de IA"

Documento próprio (`docs/design/design-system.md`), entregue **dentro** desta fase — a
referência cruzada do plano geral a "Fase 6" para este documento está desatualizada (a
numeração mudou desde que aquele trecho foi escrito; RAG é a Fase 6 atual). Princípios
(plano geral, seção 3.10), tornados tokens concretos:

| Token | Decisão |
|---|---|
| Tipografia | Uma família (ex.: Inter), pesos variados (400/500/600/700) — nunca uma segunda família decorativa. |
| Paleta | Identidade própria, não o roxo/azul de template de IA genérico — definida no documento de design, com contraste AA mínimo para texto sobre fundo. |
| Densidade | Alta, como ferramenta profissional (referência: Linear, Vercel, Datadog) — nunca espaçamento de landing page numa tela de lista de 500 runs. |
| Ícones | Zero emoji como ícone de interface. |
| Decoração | Zero gradiente decorativo. |
| Animação | Só onde comunica mudança de estado real (ex.: transição de status `running` → `completed`) — nunca só como enfeite. |
| Estados | Vazio e de carregamento desenhados explicitamente para cada tela (seções 3–7) — nunca um spinner genérico ou uma tela em branco sem explicação. |

**Caso de teste (visual/revisão, não automatizável como as fases anteriores):** dado o
documento de design revisado pelo orientador ou por um par, quando comparado às cinco
telas implementadas, então cada tela usa exclusivamente os tokens do documento — nenhuma
cor, fonte ou espaçamento "avulso" introduzido ad hoc numa tela específica.

---

## 3. Dashboard

Conformidade por tenant/categoria, evolução no tempo (consome `GET
/audits/summary-over-time`, seção 0.2), tipos com mais violações.

- **Dado** nenhum run ainda existe para o tenant, **quando** o Dashboard carrega,
  **então** mostra o estado vazio desenhado (seção 2), nunca um gráfico em branco sem
  explicação.
- **Dado** runs de múltiplos `entity_type` existentes, **quando** o Dashboard carrega,
  **então** a agregação por categoria reflete exatamente as contagens de
  `RunSummary` (Fase 1/3) somadas — nenhum recálculo divergente no frontend.
- **Dado** a API de resumo indisponível (erro de rede), **quando** o Dashboard carrega,
  **então** mostra um estado de erro explícito com opção de tentar de novo — nunca trava
  num carregando infinito.

---

## 4. Audit Runs

Lista com filtros (tenant — implícito pelo backend, tipo, status, período — seção 0.1),
progresso em tempo real dos runs em execução.

- **Dado** um run com `status=running`, **quando** a linha da lista é exibida, **então** o
  progresso (`processed`/`total`, Fase 5) atualiza sem recarregar a página inteira — via
  polling em `GET /audits/{id}/progress` ou o `stream` SSE (Fase 5, seção 4.3), a decidir
  na implementação.
- **Dado** `total=null` (broker ainda não respondeu, Fase 5), **quando** exibido, **então**
  a UI mostra "processando…" sem uma barra de progresso com denominador inventado — nunca
  `0/0` nem `?/0`.
- **Dado** filtros combinados (tipo + status + período), **quando** aplicados, **então** a
  URL reflete os filtros (parâmetros de query) — permite compartilhar/recarregar a mesma
  visão, não só estado efêmero de componente.

---

## 5. Report Detail

Entidade a entidade, violações agrupadas por severidade, diff visual "encontrado" vs.
"esperado", recomendação do SLM com o *rationale* (Fase 7).

- **Dado** um `EntityReport` com violações estruturais e semânticas misturadas (Fase 7,
  `detected_by`), **quando** exibido, **então** a origem de cada violação (Nível 1/Nível 2)
  é visualmente distinguível — nunca apresentada como uma lista homogênea que esconde de
  onde veio o achado.
- **Dado** `semantic_analysis_skipped=true` (Fase 7, seção 4), **quando** exibido,
  **então** a tela comunica explicitamente "análise semântica não executada" (com o motivo,
  se disponível) — nunca omite a seção como se o Nível 2 tivesse rodado e não achado nada.
- **Dado** uma `Recommendation` com `proposed_patch` estruturado, **quando** exibida,
  **então** o diff visual mostra claramente o valor atual vs. o `proposed_patch` — nunca só
  o `rationale` em texto sem o dado estruturado ao lado.

---

## 6. Natural Language

Caixa de comando que traduz para uma chamada de auditoria (consome `POST
/audits/interpret`, seção 0.3), **sempre com confirmação humana antes de executar**.

- **Dado** um comando interpretado com `confidence` alto e `entity_type` identificado,
  **quando** o usuário vê o resultado, **então** a tela mostra a interpretação (tipo,
  filtros) e só dispara `POST /audits` (Fase 5) após um clique explícito de confirmação —
  **nunca** auto-executa a partir da interpretação sozinha, mesmo com confiança alta.
- **Dado** `entity_type=None`/`confidence` baixo, **quando** o usuário vê o resultado,
  **então** a tela comunica que não entendeu o suficiente para prosseguir, sem oferecer um
  botão de confirmação para uma interpretação vazia.
- **Dado** o usuário edita manualmente a interpretação antes de confirmar (ex.: corrige o
  tipo sugerido), **quando** confirma, **então** `POST /audits` usa os valores editados,
  não os originalmente interpretados — a interpretação é um rascunho, nunca a fonte de
  verdade final.

---

## 7. Catalog

Quais data models estão indexados, quando foram sincronizados (Fase 2,
`CatalogIndex`/`SyncResult` — hoje só usado internamente, sem endpoint HTTP; esta fase
precisa de um `GET /catalog` simples expondo isso, mesmo padrão de "endpoint que faltava"
da seção 0).

- **Dado** o catálogo sincronizado pela última vez há N dias, **quando** a tela carrega,
  **então** mostra a data da última sincronização — nunca omite essa informação, que é
  justamente o que permite ao usuário avaliar se o catálogo pode estar desatualizado.
- **Dado** uma sincronização que falhou (Fase 2, `SyncResult.success=False`), **quando** a
  tela carrega, **então** mostra o catálogo local (última sincronização bem-sucedida) com
  um aviso explícito, nunca escondendo a falha nem servindo dado stale como se fosse atual.

---

## 8. Fora de escopo desta fase

- **Desktop.** Decisão registrada como ADR (plano geral, seção 3.11): não há nada de local
  para um app desktop fazer com SLM e banco na nuvem — se houver demanda futura, o caminho
  é Tauri, nunca Electron. Esta fase não constrói nenhum shell desktop.
- **Deploy/Terraform** (Fase 9) — esta fase entrega o frontend rodando localmente
  (`ng serve` / build estático) contra a API já existente (Fases 4–5), sem infraestrutura
  de produção.
- **Internacionalização** — fora do escopo do TCC; interface em português, mesmo idioma da
  documentação (plano geral, seção 1.3 — só o código é em inglês).

---

## 9. Definição de pronto da Fase 8

- Os três endpoints da seção 0 implementados e testados no mesmo padrão das fases
  anteriores (`ASGITransport` + fakes, unitário).
- As cinco telas (seções 3–7) implementadas, cada uma com estado vazio, de carregamento e
  de erro desenhados — nenhuma tela "nua" sem esses três estados.
- Documento de design (seção 2) existe e as telas o seguem, verificável por revisão visual.
- Fluxo da tela "Natural Language" (seção 6) comprovadamente nunca executa uma auditoria
  sem confirmação explícita — este é o único requisito de segurança de UX desta fase, e é
  o que evita o sistema "fazer algo que o usuário não pediu" a partir de uma interpretação
  de linguagem natural imprecisa.
- Nenhum teste desta fase depende de infraestrutura Terraform/AWS (Fase 9) — o frontend
  roda contra a API local (`docker-compose`, Fases 0/4) sem nenhuma dependência de nuvem
  além do que as Fases 4–7 já exigem (Orion, Postgres, Ollama).
