# Specs — Fase 6: RAG (Metodologia de Auditoria)

Mesmo formato das fases anteriores: contrato + casos de teste dado/quando/então, prontos
para virar testes antes da implementação. Cobre o `KnowledgeRetrieverPort`, o corpus curado,
o pipeline de ingestão e o `PgVectorRetriever` (plano geral, seção 3.4).

**Escopo desta fase, para não repetir o erro que a seção 3.4 do plano geral corrigiu:** o
RAG aqui **não** indexa o schema de nenhum Smart Data Model específico — isso continua
vindo por busca direta e ao vivo via `SchemaCatalogPort` (Fase 2), porque o schema muda por
natureza e reindexá-lo a cada auditoria seria custo e complexidade desnecessários. O que
esta fase indexa é conhecimento **estável**, curado pelo time, sobre *como julgar*
conformidade semântica — convenções entre modelos, casos anotados, sinônimos, estilo de
recomendação. Esta fase também **não** integra o retriever ao `RunAuditUseCase` nem ao SLM
— construir a *query* a partir de uma `Violation` real e decidir quando acionar o Nível 2 é
trabalho da Fase 7. O critério de pronto aqui é: dado um texto de query representativo de um
tipo de violação, o retriever devolve chunks relevantes do corpus — testado com embeddings
reais, não mockados, já que o corpus é pequeno o bastante para isso ser rápido.

---

## 1. Porta de domínio — `KnowledgeRetrieverPort`

```python
# domain/ports/knowledge_retriever_port.py — único ponto que a Aplicação (Fase 7) conhece

class KnowledgeCategory(str, Enum):
    CONVENTION = "convention"                    # padrões entre modelos (nomenclatura, unidades, formatos)
    ANNOTATED_CASE = "annotated_case"             # entidade incorreta -> explicação -> correção
    SYNONYM_GLOSSARY = "synonym_glossary"         # temp -> temperature, hum -> humidity, etc.
    RECOMMENDATION_STYLE = "recommendation_style" # exemplos de boas recomendações já validadas

@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str             # id estável da entrada curada de origem (ver seção 2)
    category: KnowledgeCategory
    content: str               # texto normalizado do chunk (ver seção 3, to_chunk_text)
    similarity: float          # 0.0-1.0, maior = mais relevante — nunca ordenado ao contrário
    tags: tuple[str, ...]      # ex.: ("attribute-naming", "unitCode") — livre, definido na curadoria

class KnowledgeRetrieverPort(Protocol):
    async def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        """Busca vetorial no corpus curado (seção 2). `query` é texto livre —
        esta porta não sabe nada sobre `Violation` nem sobre o domínio de
        auditoria; quem decide o que colocar na query é quem chama (Fase 7).
        Resultados vêm ordenados por `similarity` decrescente."""
```

`retrieve()` recebe uma string, não um `Violation` — decisão deliberada: acopla esta porta
só ao conceito de busca semântica, não às formas de dado da Fase 7 (que ainda não existem
quando esta fase é implementada). `RetrievedChunk.similarity` fica exposto porque a decisão
de "isso é relevante o suficiente para usar no prompt do SLM" é da Fase 7, não desta porta
— ver seção 8 (fora de escopo).

### 1.1 Casos de teste (contrato)

- **Dado** um corpus vazio (nenhum chunk indexado), **quando** `retrieve()` é chamado,
  **então** retorna `[]` — nunca levanta exceção por ausência de resultados.
- **Dado** mais chunks relevantes no índice do que `top_k`, **quando** `retrieve(query,
  top_k=3)` é chamado, **então** retorna exatamente 3 resultados, ordenados por
  `similarity` decrescente.
- **Dado** `top_k` maior que o número total de chunks indexados, **quando** `retrieve()` é
  chamado, **então** retorna todos os chunks disponíveis, sem erro, sem duplicar nenhum.
- **Dado** dois chunks de categorias diferentes igualmente relevantes para a mesma query,
  **quando** `retrieve()` é chamado, **então** ambos aparecem no resultado com o `category`
  correto — a porta não filtra por categoria sozinha, quem chama decide se quer.

---

## 2. O corpus curado — estrutura em disco (plano geral, seção 3.4)

Curadoria do time, versionada no repositório (nunca gerada em runtime, nunca scraping de
schema ao vivo). Vive em `knowledge/`, um arquivo YAML por categoria — reaproveita o nome de
diretório já usado no projeto anterior a este refactor, com conteúdo inteiramente novo:

```
knowledge/
├── conventions.yaml
├── annotated_cases.yaml
├── synonyms.yaml
└── recommendation_style.yaml
```

Cada entrada tem um `id` estável (âncora do upsert idempotente na ingestão, seção 7) e é
**um chunk inteiro** — nunca um fragmento cortado por tamanho (seção 3). Formato por
categoria:

```yaml
# knowledge/conventions.yaml
- id: convention-unit-code-un-cefact
  tags: [unitCode, units]
  statement: >
    O atributo `unitCode` segue o Common Code da UN/CEFACT Recommendation 20 (ex.: "LUX"
    para lux, "CEL" para grau Celsius) — nunca um símbolo livre como "lux" ou "°C".

- id: convention-attribute-naming-lower-camel-case
  tags: [attribute-naming]
  statement: >
    Nomes de atributo usam lowerCamelCase (ex.: `illuminanceLevel`, `dateModified`) — nunca
    snake_case nem kebab-case, mesmo que a fonte de dados original use outra convenção.

- id: convention-datetime-iso8601-with-timezone
  tags: [datetime, dateCreated, dateModified]
  statement: >
    Atributos de data/hora (`dateCreated`, `dateModified`, etc.) são ISO 8601 completo, com
    horário e fuso explícito (ex.: "2024-01-01T00:00:00Z") — nunca só a data, que é
    ambígua sobre o instante exato do evento.

- id: convention-geoproperty-is-geojson
  tags: [location, geoproperty]
  statement: >
    Atributos geográficos (`location`, `areaServed`) carregam a estrutura GeoJSON completa
    (`{"type": "Point", "coordinates": [lon, lat]}`) — nunca um par de números soltos.
```

```yaml
# knowledge/annotated_cases.yaml
- id: case-lum-instead-of-illuminance-level
  tags: [attribute-naming, illuminanceLevel]
  incorrect_example: '{"lum": {"type": "Number", "value": 0.7}}'
  explanation: >
    "lum" é uma abreviação informal; o Smart Data Model Streetlighting define o atributo
    canônico como `illuminanceLevel`. Abreviações quebram interoperabilidade — quem consome
    a entidade esperando o nome do schema não encontra o dado.
  correction: '{"illuminanceLevel": {"type": "Number", "value": 0.7}}'

- id: case-date-only-instead-of-full-iso8601
  tags: [datetime, dateCreated]
  incorrect_example: '{"dateCreated": {"type": "DateTime", "value": "2024-01-01"}}'
  explanation: >
    Falta o componente de horário e fuso — "2024-01-01" não distingue o instante exato
    dentro do dia, e sistemas que comparam timestamps podem interpretar isso de formas
    diferentes.
  correction: '{"dateCreated": {"type": "DateTime", "value": "2024-01-01T00:00:00Z"}}'

- id: case-location-as-bare-coordinates
  tags: [location, geoproperty]
  incorrect_example: '{"location": {"type": "geo:json", "value": [-46.63, -23.55]}}'
  explanation: >
    O `value` de um GeoProperty precisa ser um objeto GeoJSON completo — um array de dois
    números não diz, por si só, se é um Point, e a ordem lon/lat é fonte comum de erro.
  correction: >
    {"location": {"type": "geo:json", "value": {"type": "Point", "coordinates": [-46.63, -23.55]}}}
```

```yaml
# knowledge/synonyms.yaml
- id: synonym-illuminance-level
  canonical: illuminanceLevel
  seen_as: [lum, illuminance, luminosity]

- id: synonym-temperature
  canonical: temperature
  seen_as: [temp, tempC, temperatura]

- id: synonym-humidity
  canonical: humidity
  seen_as: [hum, umidade]

- id: synonym-address
  canonical: address
  seen_as: [addr, endereco]
```

```yaml
# knowledge/recommendation_style.yaml
- id: style-required-property-missing
  tags: [required_property_missing]
  example_rationale: >
    A propriedade é exigida pelo schema oficial do modelo e não afeta significado de
    negócio ambíguo — adicioná-la com um valor plausível resolve a não conformidade sem
    exigir decisão do operador.
  example_patch: '{"status": {"type": "Text", "value": "ok"}}'

- id: style-malformed-attribute
  tags: [malformed_attribute]
  example_rationale: >
    O atributo já existe com o valor certo, só falta o envelope NGSI-v2 — a correção é
    estrutural (reembrulhar o valor), nunca uma suposição sobre o dado em si.
  example_patch: '{"illuminanceLevel": {"type": "Number", "value": "<valor atual preservado>"}}'
```

### 2.1 `CorpusLoader`

```python
@dataclass(frozen=True)
class RawCorpusEntry:
    chunk_id: str
    category: KnowledgeCategory
    tags: tuple[str, ...]
    fields: dict  # campos específicos da categoria (statement / incorrect_example+
                  # explanation+correction / canonical+seen_as / example_rationale+example_patch)

class CorpusLoader:
    def load_all(self, corpus_dir: Path = KNOWLEDGE_DIR) -> list[RawCorpusEntry]: ...
```

### 2.2 Casos de teste

- **Dado** os quatro arquivos reais em `knowledge/` (não fixtures de teste), **quando**
  `load_all()` é chamado, **então** retorna pelo menos uma entrada de cada
  `KnowledgeCategory` — prova viva de que o corpus inicial não está vazio.
- **Dado** um arquivo de corpus com dois `id` iguais, **quando** `load_all()` é chamado,
  **então** levanta `CorpusValidationError` identificando o `id` duplicado — nunca ingere
  uma entrada ambígua silenciosamente.
- **Dado** uma entrada de `annotated_cases.yaml` sem o campo obrigatório `correction`,
  **quando** `load_all()` é chamado, **então** levanta `CorpusValidationError` apontando o
  `id` e o campo faltante — cada categoria tem seus campos obrigatórios validados na carga,
  não silenciosamente ignorados na hora de gerar o chunk.
- **Dado** um `id` que não segue o padrão `<categoria-curta>-<slug>` (convenção de nomeação
  usada nos exemplos acima), **quando** `load_all()` é chamado, **então** ainda carrega
  normalmente — a convenção de nomeação de `id` é estilo, não validação obrigatória.

---

## 3. Normalização em chunk — `to_chunk_text`

Chunking "por caso/regra, não por tamanho fixo" (plano geral, seção 3.4) significa que cada
`RawCorpusEntry` **já é** um chunk — o trabalho aqui é renderizar seus campos estruturados
num texto único e coerente, pronto para ser embutido (seção 4) e, na Fase 7, mostrado no
prompt do SLM. Nunca parte um caso ao meio.

```python
def to_chunk_text(entry: RawCorpusEntry) -> str: ...
```

### 3.1 Casos de teste

- **Dado** uma entrada de `ANNOTATED_CASE`, **quando** `to_chunk_text()` é chamado,
  **então** o texto resultante contém, nesta ordem, o exemplo incorreto, a explicação e a
  correção — nunca um fragmento isolado sem o contexto completo do caso.
- **Dado** uma entrada de `SYNONYM_GLOSSARY` com múltiplos sinônimos para o mesmo atributo
  canônico, **quando** `to_chunk_text()` é chamado, **então** todos os sinônimos aparecem
  no mesmo texto — uma busca por qualquer um deles (`temp`, `tempC` ou `temperatura`) precisa
  poder recuperar este único chunk, não um chunk por sinônimo.
- **Dado** uma entrada de `CONVENTION`, **quando** `to_chunk_text()` é chamado, **então** o
  texto é exatamente o `statement` (sem campos extras nem formatação que não exista na
  fonte) — categoria mais simples, sem composição de múltiplos campos.
- **Dado** a mesma `RawCorpusEntry`, **quando** `to_chunk_text()` é chamado duas vezes,
  **então** o resultado é idêntico byte a byte — determinístico, condição necessária para o
  upsert idempotente da seção 7 não recalcular embedding à toa.

---

## 4. `Embedder` — decisão de modelo (nunca um port de domínio)

`embedder.py` vive em `infrastructure/rag/`, não em `domain/ports/` (ver árvore de
diretórios do plano geral, seção 2.2) — só `KnowledgeRetrieverPort` é visível pra
Aplicação; embutir texto é detalhe de implementação do `PgVectorRetriever` e da ingestão,
nunca algo que a Fase 7 chama diretamente.

**Decisão de modelo**, no mesmo espírito honesto da seção 1.1/1.2 do plano geral: dado que
o corpus é pequeno e estável (reindexação é evento raro, seção 3.4) e o AWS Academy Learner
Lab não comporta GPU ligada continuamente (seção 1.1), tanto a indexação quanto a busca por
query usam um modelo local, CPU-only, sem custo de API nem dependência de rede —
`sentence-transformers/all-MiniLM-L6-v2` (384 dimensões, ~80MB, bem estabelecido para
similaridade semântica em textos curtos). Ainda assim definido atrás de um `Protocol`, pelo
mesmo motivo da seção 3.5 do plano geral ("a troca dev↔produção é certa e barata de prever
agora, cara de retrofitar depois") — uma futura troca por um serviço de embeddings
gerenciado (ex.: Bedrock) não deve exigir mudar `PgVectorRetriever` nem a migration.

```python
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class SentenceTransformersEmbedder:
    """Roda o modelo localmente, CPU-only. `embed()` despacha para
    `asyncio.to_thread` — a biblioteca é síncrona."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None: ...
```

### 4.1 Casos de teste

- **Dado** o mesmo texto embutido duas vezes, **quando** `embed()` é chamado, **então** os
  vetores retornados são idênticos — determinístico, o modelo local em modo de inferência
  não introduz aleatoriedade.
- **Dado** dois textos semanticamente próximos (ex.: `"lum"` e `"illuminanceLevel, nível de
  iluminância"`) e um terceiro sem relação nenhuma (ex.: `"política de retenção de logs"`),
  **quando** `embed()` é chamado para os três, **então** a similaridade de cosseno entre os
  dois primeiros é maior que entre qualquer um deles e o terceiro — prova viva de que o
  modelo escolhido captura similaridade semântica útil ao domínio, não só sintática.
- **Dado** uma lista vazia, **quando** `embed()` é chamado, **então** retorna `[]` sem
  carregar/chamar o modelo.
- **Dado** uma lista com N textos, **quando** `embed()` é chamado, **então** retorna
  exatamente N vetores, cada um com 384 dimensões, na mesma ordem da entrada.

---

## 5. `knowledge_chunks` — tabela e migration

Migration aditiva sobre a extensão `vector` já criada na migration inicial da Fase 3
(reservada explicitamente para esta fase — ver comentário em
`migrations/versions/2f62abb9e945_initial_schema.py`). Requer o pacote Python `pgvector`
(tipo `Vector` para SQLAlchemy) como nova dependência.

```python
# infrastructure/persistence/tables.py — nova tabela
knowledge_chunks_table = Table(
    "knowledge_chunks", metadata,
    Column("chunk_id", String, primary_key=True),   # = RawCorpusEntry.chunk_id — nunca um uuid gerado
    Column("category", String, nullable=False),
    Column("content", String, nullable=False),
    Column("tags", JSONB, nullable=False, server_default="[]"),
    Column("embedding", Vector(384), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
# indice de similaridade: HNSW, cosine distance (pgvector >= 0.5.0)
Index(
    "ix_knowledge_chunks_embedding_cosine", knowledge_chunks_table.c.embedding,
    postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
)
```

`chunk_id` como chave primária (não um UUID à parte) é o que torna o upsert da seção 7 uma
única operação por `id` de origem — nunca precisa de uma tabela de mapeamento auxiliar.

### 5.1 Casos de teste (integração, Postgres real)

- **Dado** a extensão `vector` já criada (Fase 3), **quando** a migration desta fase é
  aplicada (`alembic upgrade head`), **então** a tabela `knowledge_chunks` existe com a
  coluna `embedding` do tipo `vector(384)` e o índice HNSW de similaridade por cosseno.
- **Dado** a migration aplicada, **quando** revertida (`alembic downgrade -1`), **então** a
  tabela é removida sem erro — mesma exigência de `downgrade()` funcional da Fase 3, seção
  9.
- **Dado** duas linhas inseridas com o mesmo `chunk_id`, **quando** a segunda inserção é
  uma tentativa de `INSERT` simples (não upsert), **então** o banco rejeita por violação de
  chave primária — a unicidade é garantida pelo schema, não só pela disciplina da aplicação.

---

## 6. `PgVectorRetriever` — implementa `KnowledgeRetrieverPort`

```python
class PgVectorRetriever:
    def __init__(self, engine: AsyncEngine, embedder: Embedder) -> None: ...

    async def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        """Embute `query` via Embedder, ordena knowledge_chunks por distância
        de cosseno (`embedding <=> :query_embedding`) e devolve os top_k mais
        próximos como similaridade (1 - distância)."""
```

### 6.1 Casos de teste (integração, Postgres real + `SentenceTransformersEmbedder` real —
não mockado; o corpus é pequeno o bastante para isso ser rápido)

- **Dado** o corpus curado completo (seção 2) ingerido (seção 7), **quando**
  `retrieve("atributo 'lum' fora do padrão de nomenclatura", top_k=3)` é chamado, **então**
  o chunk `synonym-illuminance-level` aparece entre os 3 primeiros resultados — este é
  literalmente o critério de pronto da fase, tornado executável.
- **Dado** o mesmo corpus ingerido, **quando** `retrieve("data sem horário nem fuso",
  top_k=3)` é chamado, **então** `case-date-only-instead-of-full-iso8601` e
  `convention-datetime-iso8601-with-timezone` aparecem entre os resultados — prova que
  categorias diferentes (caso anotado e convenção) sobre o mesmo tema são recuperáveis pela
  mesma query.
- **Dado** um índice vazio (nenhuma ingestão ainda rodou), **quando** `retrieve()` é
  chamado, **então** retorna `[]` — comportamento idêntico ao caso de teste de contrato da
  seção 1.1, agora contra o banco real.
- **Dado** `top_k` maior que o total de chunks no índice, **quando** `retrieve()` é
  chamado, **então** retorna todos os chunks, sem erro, sem duplicar — mesmo caso de teste
  de contrato, contra o banco real.

---

## 7. Ingestão — `SyncKnowledgeBaseUseCase`

Orquestra `CorpusLoader` → `to_chunk_text()` → `Embedder.embed()` (em lote) → upsert em
`knowledge_chunks` por `chunk_id` → remove do índice qualquer `chunk_id` que não exista mais
no corpus atual. Análogo, em espírito, ao `SyncCatalogUseCase` da Fase 2
(`application/use_cases/sync_schema_catalog.py`) — mesma ideia de sincronização idempotente
e auditável, aplicada ao corpus do RAG em vez do catálogo de modelos.

```python
@dataclass(frozen=True)
class KnowledgeSyncResult:
    created: int
    updated: int
    deleted: int
    total: int

class SyncKnowledgeBaseUseCase:
    def __init__(self, corpus_loader: CorpusLoader, embedder: Embedder, engine: AsyncEngine) -> None: ...
    async def execute(self) -> KnowledgeSyncResult: ...
```

### 7.1 Casos de teste (integração, Postgres real)

- **Dado** o corpus sem nenhuma mudança desde a última sincronização, **quando**
  `execute()` é chamado de novo, **então** `created == updated == deleted == 0` — upsert
  por `chunk_id` idempotente, reindexação repetida não duplica nem recalcula à toa.
- **Dado** uma entrada nova adicionada a um dos arquivos YAML desde a última sincronização,
  **quando** `execute()` é chamado, **então** `created == 1` e a nova linha existe em
  `knowledge_chunks` com embedding calculado.
- **Dado** uma entrada existente com o `content` alterado (mesmo `chunk_id`, texto
  revisado pela curadoria), **quando** `execute()` é chamado, **então** `updated == 1` e o
  embedding da linha é recalculado — nunca serve busca com um embedding desatualizado do
  texto antigo.
- **Dado** uma entrada removida de um arquivo YAML desde a última sincronização, **quando**
  `execute()` é chamado, **então** `deleted == 1` e a linha correspondente some de
  `knowledge_chunks` — o índice nunca acumula "lixo" de entradas que não existem mais na
  fonte curada.
- **Dado** o corpus real completo (seção 2), **quando** `execute()` é chamado pela primeira
  vez contra um banco vazio, **então** `total` reflete o número total de entradas nos
  quatro arquivos YAML, e uma chamada subsequente a `PgVectorRetriever.retrieve()` já
  encontra resultados (integra com o caso de teste da seção 6.1).

---

## 8. Fora de escopo desta fase

- **Nenhuma integração com `RunAuditUseCase` ou com o SLM.** Construir a *query* de busca a
  partir de uma `Violation` real, decidir um limiar de `similarity` para usar ou descartar
  um resultado, e decidir quando acionar o Nível 2 (seção 1.2/3.5 do plano geral) — tudo
  isso é Fase 7.
- **Nenhuma mudança em `SchemaCatalogPort`** nem no fluxo de busca direta do schema (Fase
  2). O corpus desta fase nunca contém o `schema.json` de um Smart Data Model específico —
  ver nota de escopo no topo deste documento.
- **Nenhum endpoint HTTP nem comando CLI novo é obrigatório.** `container.py` só precisa
  expor `get_embedder()`/`get_knowledge_retriever()` (para a Fase 7 consumir depois); a
  sincronização do corpus (seção 7) pode ser um script administrativo simples nesta fase,
  do mesmo jeito que a sincronização do catálogo (Fase 2, seção 2.2) também não foi
  exigida via CLI/endpoint naquela fase.

---

## 9. Definição de pronto da Fase 6

- Todos os casos de teste acima implementados e passando.
- `knowledge/` com os quatro arquivos YAML povoados com conteúdo real e defensável (não
  placeholders) — pelo menos os exemplos das seções 2 acima, cobrindo as quatro categorias.
- `CorpusLoader`/`to_chunk_text()` testados sem banco nem rede (puros, síncronos).
- `SentenceTransformersEmbedder`, `PgVectorRetriever` e `SyncKnowledgeBaseUseCase` testados
  com **Postgres real via testcontainers** e o modelo de embedding real (não mockado) — o
  corpus é pequeno o bastante para isso rodar rápido; nenhum teste desta fase depende de uma
  API externa de embeddings estar no ar.
- Migration da seção 5 aplica e reverte sem erro num banco limpo com a extensão `vector` já
  presente.
- Critério de pronto do plano geral, tornado executável: dado o corpus ingerido, uma query
  representativa de um tipo de violação real (ex.: `"atributo 'lum' fora do padrão de
  nomenclatura"`) devolve o chunk de sinônimos/convenção correspondente entre os primeiros
  resultados — e nenhum teste desta fase depende de `SchemaCatalogPort` nem de
  `SemanticAnalyzerPort` (Fase 7), mesma disciplina de isolamento entre fases já usada na
  Fase 3, seção 10.
