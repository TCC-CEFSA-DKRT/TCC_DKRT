# Specs — Fase 7: Nível 2 (SemanticAnalyzer / SLM)

Mesmo formato das fases anteriores: contrato + casos de teste dado/quando/então. Cobre o
`SemanticAnalyzerPort`, o `OllamaAnalyzer` (Qwen2.5 local, dev), a integração ao
`RunAuditUseCase` e o controle de custo que decide quando o SLM roda (plano geral, seções
1.2 e 3.5). **É esta fase que prova a contribuição científica do TCC** — o momento em que o
sistema detecta algo que o Nível 1, puramente estrutural, comprovadamente não pega.

---

## 1. Porta de domínio — `SemanticAnalyzerPort`

```python
# domain/ports/semantic_analyzer_port.py

@dataclass(frozen=True)
class SemanticAnalysisContext:
    entity_id: str
    entity_type: EntityType
    plain_values: dict                      # NgsiV2Mapper.to_plain_values() — Fase 4
    schema: dict                             # ResolvedSchema.content — Fase 2
    structural_violations: tuple[Violation, ...]   # Nível 1, pode ser vazia (caso b, seção 3)
    knowledge_chunks: tuple[RetrievedChunk, ...]   # Fase 6, já recuperados por quem monta o contexto

@dataclass(frozen=True)
class SemanticAnalysisResult:
    violations: tuple[Violation, ...] = ()          # sempre detected_by=DetectionSource.SEMANTIC
    recommendations: tuple[Recommendation, ...] = ()
    analysis_unavailable: bool = False       # ver seção 2 — nunca confundir com "nada encontrado"

class SemanticAnalyzerPort(Protocol):
    async def analyze(self, ctx: SemanticAnalysisContext) -> SemanticAnalysisResult:
        """Nunca levanta exceção para fora — falha de rede, timeout ou saída
        do modelo que não valida vira `analysis_unavailable=True` (seção 2).
        Uma falha do SLM nunca derruba o `AuditRun` inteiro: é uma
        degradação silenciosa e explícita, não uma `ContextBrokerUnavailableError`
        (Fase 4) — o Nível 1 já persistiu um resultado válido antes de o
        Nível 2 sequer ser chamado (seção 4)."""
```

`plain_values`/`schema` chegam prontos (a porta não sabe nada sobre `NgsiV2Mapper` nem
`SchemaCatalogPort`); `knowledge_chunks` também chegam prontos (a porta não chama
`KnowledgeRetrieverPort` — quem monta o contexto, seção 4, decide a query de busca). O
analisador só analisa; não busca nada por conta própria.

`analysis_unavailable=True` sempre vem acompanhado de `violations=()` e
`recommendations=()` — nunca uma mistura de resultado parcial confiável com o resto
descartado; se a saída do modelo não valida, **nada** dela é usado.

---

## 2. Contrato de saída — validado, nunca texto livre

O prompt exige JSON estruturado (formato abaixo). A resposta crua do modelo passa por
validação Pydantic antes de qualquer coisa virar `Violation`/`Recommendation` de domínio —
nunca confiar em texto livre do modelo para alimentar o banco.

```python
class _SemanticFindingSchema(BaseModel):
    attribute_path: str
    severity: Literal["error", "warning", "info"]
    rule: str
    message: str

class _SemanticRecommendationSchema(BaseModel):
    attribute_path: str
    action: Literal["rename_attribute", "add_missing_attribute", "fix_type", "fix_format"]
    proposed_patch: dict
    rationale: str
    confidence: float

class _SemanticAnalysisOutputSchema(BaseModel):
    findings: list[_SemanticFindingSchema] = []
    recommendations: list[_SemanticRecommendationSchema] = []
```

### 2.1 Casos de teste

- **Dado** uma resposta JSON sintaticamente válida e conforme
  `_SemanticAnalysisOutputSchema`, **quando** o adaptador processa a resposta, **então**
  `SemanticAnalysisResult` é populado com `Violation(detected_by=SEMANTIC)` e
  `Recommendation` correspondentes, `analysis_unavailable=False`.
- **Dado** uma resposta que não é JSON válido (o modelo "conversou" em vez de responder só
  o objeto), **quando** processada, **então** `analysis_unavailable=True`, sem exceção
  propagada para fora do adaptador.
- **Dado** um JSON sintaticamente válido mas faltando um campo obrigatório do schema (ex.:
  `recommendations[0]` sem `confidence`), **quando** processado, **então**
  `analysis_unavailable=True` — mesmo tratamento do caso anterior, a validação Pydantic é
  quem decide, não uma tentativa de "salvar o que dá".
- **Dado** um JSON válido mas com `confidence` fora de `[0.0, 1.0]` (rejeitado pelo
  invariante de `Recommendation.__post_init__`, Fase 1), **quando** o adaptador tenta
  construir o `Recommendation` de domínio, **então** captura `InvalidRecommendationError` e
  trata como `analysis_unavailable=True` — o adaptador nunca deixa uma exceção de invariante
  de domínio vazar para o `RunAuditUseCase` a partir de uma saída de modelo não confiável.
- **Dado** `findings=[]` e `recommendations=[]` (o modelo respondeu corretamente que não
  encontrou nada de semanticamente relevante), **quando** processado, **então**
  `SemanticAnalysisResult(violations=(), recommendations=(), analysis_unavailable=False)` —
  distinto do caso `analysis_unavailable=True`: "nada encontrado" é um resultado válido,
  "não consegui confiar na resposta" não é.

---

## 3. Regra de acionamento do Nível 2 (REVISADA pela ADR-0014, 2026-09-09)

> **Superseded.** A tabela e os casos de teste abaixo descrevem a regra ORIGINAL desta
> fase (controle de custo — plano geral, seção 1.2/3.5), mantida aqui por registro
> histórico. A ADR-0014 revisou essa regra: um Smart Data Model tem ligação semântica
> forte que o Nível 1 (puramente estrutural) não esgota, e restringir o Nível 2 a só
> refinar o que o Nível 1 já reprovou deixava fora de alcance exatamente a categoria de
> erro mais relevante (entidade estruturalmente perfeita, semanticamente incoerente). A
> regra vigente é: **o Nível 2 roda sempre que o Nível 1 resolve um schema e produz
> `plain_values` válidos — inclusive para `CONFORMANT`.** Só `NO_MODEL_FOUND`,
> `SCHEMA_UNAVAILABLE` e envelope NGSI-v2 malformado continuam sem acionar o SLM (não há
> contexto coerente para montar). Ver ADR-0014 para a decisão completa e o trade-off de
> custo/latência aceito (mitigado pela GPU da ADR-0015).

Regra original (histórico, refinada em termos do que o `StructuralValidator`, Fase 1, de
fato produz):

| `EntityReport.status` (Nível 1, antes do Nível 2) | Aciona o SLM? (regra original) | Por quê |
|---|---|---|
| `CONFORMANT` (zero violações) | Não | Nenhum sinal do Nível 1 para o Nível 2 refinar — inclui o caso conhecido em que `additionalProperties: true` (padrão permissivo) deixa um atributo extra não mapeado (ex.: um `"temp"` sobrando ao lado de um `"temperature"` já correto) completamente invisível ao Nível 1. |
| `NON_CONFORMANT` (≥1 violação `ERROR`) | Sim | Caso principal — inclui o cenário `temp`/`temperature` do plano geral: `temperature` ausente gera `required_property_missing` (Nível 1); o Nível 2 recebe `plain_values` **completo** (incluindo o `"temp"` não reconhecido) + o glossário de sinônimos (Fase 6) e pode sugerir `rename_attribute` em vez do genérico `add_missing_attribute` que o Nível 1, sozinho, não tem como diferenciar. |
| `PARTIAL` (só violações `WARNING`, hoje só `unexpected_property` quando `additionalProperties: false`) | Sim | Atributo extra explicitamente rejeitado pelo schema é justamente o tipo de sinal que vale a pena o SLM examinar (pode ser ruído, pode ser um atributo válido com nome errado). |
| `NO_MODEL_FOUND` / `SCHEMA_UNAVAILABLE` | Não | Sem schema, não há `plain_values` compatíveis nem violações estruturais para formar contexto útil. Continua valendo depois da ADR-0014 — não mudou. |

### 3.1 Casos de teste (ATUALIZADOS pela ADR-0014 — ver `tests/unit/application/test_run_audit_use_case.py::TestSemanticAnalysisTriggering`)

- **Dado** um lote de 1000 entidades onde 900 são `CONFORMANT` e 100 são
  `NON_CONFORMANT`/`PARTIAL`, **quando** `RunAuditUseCase` processa o lote, **então**
  `SemanticAnalyzerPort.analyze()` é chamado exatamente **1000** vezes — as 900
  `CONFORMANT` chamam também, desde a ADR-0014 (regra original, histórica: só as 100
  chamavam).
- **Dado** uma entidade `NO_MODEL_FOUND`, **quando** processada, **então**
  `analyze()` **não** é chamado — o relatório final tem `semantic_analysis_skipped=True`
  (regra inalterada pela ADR-0014).
- **Dado** uma entidade `CONFORMANT`, mesmo com atributos não declarados no schema (caso
  `additionalProperties: true` da tabela acima), **quando** processada, **então**
  `analyze()` **é** chamado (invertido da regra original pela ADR-0014) e
  `semantic_analysis_skipped=False`.

---

## 4. Integração ao `RunAuditUseCase._build_report` (Fase 4)

Pseudocódigo ATUALIZADO pela ADR-0014 — sem o `if status_from(...) not in {...}` que
existia aqui antes (regra histórica, ver seção 3): a partir do momento em que
`resolve_data_model`/`fetch_schema`/`to_plain_values` terminam sem erro, o Nível 2 roda
incondicionalmente.

```
_build_report(raw_entity):
    ... (Nível 1, inalterado: resolve_data_model, fetch_schema, to_plain_values, validate)
    structural_violations = validator.validate(plain_values, schema.content)

    # ADR-0014: sem gate por status — chega aqui so' quem tem schema+plain_values
    # validos (NO_MODEL_FOUND/SCHEMA_UNAVAILABLE/envelope malformado ja' retornaram
    # antes, em ramos anteriores nao mostrados aqui).
    chunks = await knowledge_retriever.retrieve(query_from(structural_violations))
    result = await semantic_analyzer.analyze(SemanticAnalysisContext(
        entity_id=..., entity_type=..., plain_values=plain_values, schema=schema.content,
        structural_violations=tuple(structural_violations), knowledge_chunks=tuple(chunks),
    ))

    all_violations = [*structural_violations, *result.violations]
    final_status = ConformanceStatus.derive(all_violations, model_found=True)
    return EntityReport(
        ..., violations=all_violations, recommendations=list(result.recommendations),
        status=final_status, semantic_analysis_skipped=False,
    )
```

Dois pontos que não são óbvios na descrição em prosa acima e precisam de teste dedicado:

1. **`status` é sempre re-derivado sobre a lista combinada** (estrutural + semântica) via
   `ConformanceStatus.derive()` — nunca herdado do Nível 1 sozinho. Uma violação `ERROR`
   encontrada só pelo Nível 2 pode transformar um `PARTIAL` em `NON_CONFORMANT`; é o
   invariante de `EntityReport.__post_init__` (Fase 1) quem garante isso por construção —
   se o status final não bater com as violações combinadas, o `EntityReport` nem chega a
   ser construído.
2. **`semantic_analysis_skipped=False` significa "o Nível 2 foi chamado"**, não "o Nível 2
   encontrou algo" — mesmo quando `result.analysis_unavailable=True` (o SLM foi chamado,
   mas a resposta não pôde ser confiada), `semantic_analysis_skipped` continua `False`. É
   uma distinção diferente de `analysis_unavailable`, e os dois campos são necessários:
   "não tentamos" (economia de custo) é diferente de "tentamos e não deu pra confiar"
   (degradação do SLM).
3. **A query construída para o `KnowledgeRetrieverPort` (Fase 6) vem das
   `structural_violations`** — ex.: `f"{violation.rule} em {violation.attribute_path}"` —
   é aqui, não na Fase 6, que a ponte entre uma `Violation` real e uma busca vetorial é
   decidida (ver nota de escopo da Fase 6, seção 8).

### 4.1 Casos de teste

- **Dado** uma entidade `NON_CONFORMANT` no Nível 1 e `SemanticAnalyzerPort.analyze()`
  retornando uma nova `Violation(severity=ERROR, detected_by=SEMANTIC)`, **quando**
  `_build_report()` termina, **então** o `EntityReport.violations` contém as violações do
  Nível 1 **e** a do Nível 2, e `status` continua `NON_CONFORMANT` (já era, permanece).
- **Dado** uma entidade `PARTIAL` no Nível 1 (só `WARNING`) e `analyze()` retornando uma
  `Violation(severity=ERROR, detected_by=SEMANTIC)`, **quando** `_build_report()` termina,
  **então** `status` muda para `NON_CONFORMANT` — o Nível 2 pode **piorar** o veredito do
  Nível 1, nunca fica preso ao status que já tinha sido calculado antes dele rodar.
- **Dado** `analyze()` retornando `analysis_unavailable=True`, **quando** `_build_report()`
  termina, **então** o `EntityReport` final contém só as violações do Nível 1 (nada do
  Nível 2 é incorporado), `status` é o do Nível 1 sozinho, e
  `semantic_analysis_skipped=False` — o run **não falha** por causa disso; é uma
  degradação registrada, não um erro que interrompe o processamento (diferente de
  `ContextBrokerUnavailableError`, Fase 4).
- **Dado** uma entidade `CONFORMANT`, **quando** `_build_report()` termina, **então**
  `semantic_analysis_skipped=True` e `recommendations=[]` — nenhuma chamada ao
  `KnowledgeRetrieverPort` nem ao `SemanticAnalyzerPort` aconteceu (verificável com fakes
  que levantam `AssertionError` se chamados, mesmo padrão já usado nos testes da Fase 5
  para `start()`).

---

## 5. `OllamaAnalyzer` (dev/local) — Qwen2.5 via Ollama

```python
class OllamaAnalyzer:
    def __init__(self, client: httpx.AsyncClient, base_url: str,
                 model: str = "qwen2.5:7b-instruct") -> None: ...

    async def analyze(self, ctx: SemanticAnalysisContext) -> SemanticAnalysisResult: ...
```

Monta o prompt a partir de `ctx` (entidade + schema + violações estruturais + chunks do
RAG), chama `POST {base_url}/api/generate` (ou `/api/chat`) com `format="json"` (recurso
nativo do Ollama para forçar saída JSON) e `temperature` baixa (determinismo é mais
importante que criatividade aqui). Prompts vivem em
`infrastructure/llm/prompts/semantic_diagnosis.md` (árvore do plano geral, seção 2.2) —
texto fora do código, para poder revisar/versionar sem tocar Python.

### 5.1 Casos de teste (unitário, `httpx.MockTransport` — mesmo padrão do `OrionAdapter`, Fase 4)

- **Dado** um `SemanticAnalysisContext` com uma violação `required_property_missing` para
  `temperature` e um chunk do glossário de sinônimos (`temp -> temperature`) entre
  `knowledge_chunks`, **quando** `analyze()` monta a requisição, **então** o corpo da
  requisição contém, em algum lugar do prompt, tanto o atributo `temperature` quanto o
  chunk de sinônimo — prova de que o contexto chega inteiro ao modelo, não truncado.
- **Dado** uma resposta HTTP 200 com JSON válido, **quando** `analyze()` processa,
  **então** aplica exatamente a validação da seção 2 (reaproveitada, não duplicada aqui).
- **Dado** timeout ou erro de conexão ao chamar o Ollama, **quando** `analyze()` é
  chamado, **então** retorna `analysis_unavailable=True` — **nunca** levanta exceção (ver
  contrato da porta, seção 1); diferente de `ContextBrokerUnavailableError` (Fase 4), que
  propositalmente propaga, porque ali a falta de dado impede qualquer trabalho, enquanto
  aqui o Nível 1 já produziu um resultado válido e persistível antes do Nível 2 rodar.
- **Dado** Ollama respondendo HTTP 500, **quando** `analyze()` é chamado, **então**
  mesmo tratamento do timeout — `analysis_unavailable=True`, sem exceção.

---

## 6. `BedrockAnalyzer` — escopo desta fase é só a forma, não a implementação completa

O plano geral (seção 3.5, "Ainda em aberto") deixa em aberto se a produção usa Bedrock ou
Ollama em EC2, decisão que depende do orçamento restante do AWS Academy, verificável só na
Fase 9. Por isso, nesta fase:

- **Dentro do escopo:** `BedrockAnalyzer` existe como classe que implementa
  `SemanticAnalyzerPort` (mesmo motivo de "duas implementações desde o início" já usado em
  `JobQueuePort`, Fase 5), o suficiente para o container (seção 7) poder alternar entre os
  dois via configuração sem mudar `RunAuditUseCase`.
- **Fora do escopo:** testes de integração contra Bedrock real, ajuste fino de prompt
  específico para o modelo da AWS, e a decisão final de qual roda em produção — tudo isso
  fica para a Fase 9, com o número de orçamento em mãos (ver Parte VII, "Ainda em aberto",
  do plano geral).

---

## 7. Testes golden — detecção de regressão de prompt (plano geral, seção 6.1)

```
tests/golden/test_semantic_analyzer_golden.py
```

Um punhado de casos fixos (a começar pelo cenário `temp`/`temperature` do Streetlight, já
usado como exemplo em todo este documento) rodados contra o `OllamaAnalyzer` **real** (Qwen2.5
rodando via Ollama — precisa do ambiente local, mesmo espírito de
`tests/integration/context_broker/test_orion_adapter_integration.py`, Fase 4: não roda no
CI/sandbox sem a dependência externa disponível). A saída é comparada a um snapshot
gravado em `tests/golden/snapshots/`.

**Importante, porque é LLM:** o snapshot não compara texto livre (`rationale`,
`message`) byte a byte — mesmo em temperatura baixa, a prosa pode variar. Compara **forma**:
quais `rule`/`attribute_path`/`action` apareceram, presença/ausência de cada achado
esperado. Uma mudança de prompt ou de versão do modelo que altere a forma da resposta
(não só a prosa) é o que este teste existe para pegar.

### 7.1 Casos de teste

- **Dado** o caso fixo `temp`/`temperature` (seção 3, cenário principal), **quando** o
  teste golden roda, **então** a saída contém uma `Recommendation` com
  `action=rename_attribute` e `attribute_path` apontando para o atributo correto — se o
  modelo passar a sugerir `add_missing_attribute` em vez de `rename_attribute` para este
  caso, o teste falha, sinalizando regressão de prompt/modelo.
- **Dado** o mesmo caso fixo rodado duas vezes seguidas, **quando** comparado, **então** a
  **forma** da resposta (conjunto de `rule`/`action` encontrados) é idêntica — mesmo que a
  prosa de `rationale` varie, a decisão estrutural do modelo não deveria.

---

## 8. Fora de escopo desta fase

- Ajuste fino de custo/latência em produção (batching de chamadas ao SLM, cache de
  respostas por entidade+schema) — otimização de refinamento posterior, não bloqueia o
  critério de pronto.
- Frontend (Fase 8) e deploy/Terraform (Fase 9) — esta fase só cobre backend.
- Decisão final Bedrock vs. Ollama em EC2 para produção (seção 6).

---

## 9. Definição de pronto da Fase 7

- Todos os casos de teste acima implementados e passando.
- `OllamaAnalyzer` testado com `httpx.MockTransport` (unitário, sem Ollama real) cobrindo
  saída válida, saída malformada e falha de rede/timeout.
- Teste golden (seção 7) demonstrando, contra o Qwen2.5 real via Ollama, que o sistema
  detecta `temp` vs `temperature` — o critério de pronto do plano geral, tornado
  executável e repetível.
- `RunAuditUseCase` atualizado (seção 4) com o controle de custo da seção 3 comprovado por
  teste (contagem de chamadas ao `SemanticAnalyzerPort` num lote misto).
- `BedrockAnalyzer` existe e implementa `SemanticAnalyzerPort` (forma), sem exigir teste de
  integração contra AWS real nesta fase (seção 6).
- Nenhum teste desta fase depende do frontend (Fase 8) nem de infraestrutura Terraform
  (Fase 9) — mesma disciplina de isolamento entre fases já usada nas fases anteriores.
