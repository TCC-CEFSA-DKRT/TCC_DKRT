# Specs — Fase 2: Catálogo de Smart Data Models

Mesmo formato da Fase 1: contrato + casos de teste dado/quando/então, prontos para virar
testes antes da implementação. Cobre a resolução de modelo por tipo de entidade e o cache
em duas camadas com verificação condicional (seção 3.3 do plano geral).

---

## 1. Porta de domínio

```python
# domain/ports/schema_catalog_port.py — único ponto que a Aplicação conhece

@dataclass(frozen=True)
class ResolvedSchema:
    data_model: DataModelRef
    content: dict            # JSON Schema já parseado
    origin: SchemaOrigin     # LIVE ou CACHE(fetched_at) — ver Fase 1, seção 2.2

class SchemaCatalogPort(Protocol):
    async def resolve_data_model(self, entity_type: EntityType) -> DataModelRef | None:
        """Responde apenas 'existe um Smart Data Model para este tipo, e qual é' —
        não busca o conteúdo do schema."""

    async def fetch_schema(self, data_model: DataModelRef) -> ResolvedSchema:
        """Obtém o conteúdo do schema, aplicando a política de cache em duas
        camadas + verificação condicional (seção 3 deste documento)."""
```

Duas operações separadas de propósito: a primeira responde "esse tipo tem modelo
conhecido?" (pergunta de catálogo — raramente depende de rede, ver seção 2); a segunda
responde "qual o conteúdo atual desse schema?" (pergunta de conteúdo — a que muda por
natureza e precisa da política de cache).

---

## 2. `CatalogIndex` — resolução de tipo → modelo

Envolve a biblioteca `pysmartdatamodels`. Importante: o catálogo (lista de quais modelos
existem) vem empacotado com a biblioteca e é **raramente** dependente de rede — só a
sincronização periódica (`sync()`) precisa de rede; a consulta "esse tipo existe?" não.

```python
class CatalogIndex:
    def resolve(self, entity_type: EntityType) -> DataModelRef | None: ...
    def sync(self) -> SyncResult: ...   # chama pysmartdatamodels.update_data()
```

### 2.1 Casos de teste — resolução

- **Dado** `entity_type="Streetlight"`, que existe no catálogo (domínio Streetlighting),
  **quando** `resolve()` é chamado, **então** retorna um `DataModelRef` com
  `subject="dataModel.Streetlighting"`, `model_name="Streetlight"` e `schema_url`
  apontando para o `schema.json` correto.
- **Dado** `entity_type="TipoQueNaoExiste123"`, **quando** `resolve()` é chamado, **então**
  retorna `None` — **não** levanta exceção. Ausência no catálogo é resultado válido, não erro.
- **Dado** dois tipos com nomes parecidos mas de domínios diferentes (ex.: um `Streetlight`
  hipotético em outro domínio, se existisse), **quando** `resolve()` é chamado, **então**
  o `DataModelRef` retornado corresponde exatamente ao `subject` esperado — resolução não
  pode ser ambígua silenciosamente; se houver ambiguidade real no catálogo, o comportamento
  esperado é levantar `AmbiguousDataModelError`, nunca escolher um dos dois sem sinalizar.

### 2.2 Casos de teste — sincronização

- **Dado** um catálogo local desatualizado, **quando** `sync()` é chamado com rede
  disponível, **então** `pysmartdatamodels.update_data()` é invocado e `SyncResult.success`
  é `True`, com `models_count` refletindo o total após a sincronização.
- **Dado** ausência de rede, **quando** `sync()` é chamado, **então** `SyncResult.success`
  é `False` com o motivo registrado, e o catálogo local (última sincronização bem-sucedida)
  **continua utilizável** — uma sincronização falha não apaga o que já existia.
- **Caso de uso de aplicação** (`SyncCatalogUseCase`, ver árvore do plano geral): dado que o
  `sync()` roda periodicamente (agendado, fora do escopo de teste unitário aqui), **quando**
  invocado manualmente via CLI/endpoint administrativo, **então** o resultado é reportado
  de forma auditável (log estruturado com `models_count`, `duration_ms`, `success`).

---

## 3. Cache em duas camadas — `fetch_schema`

### 3.1 `InMemorySchemaCache`

```python
class InMemorySchemaCache:
    def get(self, entity_type: EntityType) -> ResolvedSchema | None: ...
    def set(self, entity_type: EntityType, schema: ResolvedSchema) -> None: ...
```

**Casos de teste:**
- **Dado** um schema recém-inserido no cache de memória, **quando** `get()` é chamado logo
  em seguida, **então** retorna o schema sem qualquer chamada externa.
- **Dado** um schema inserido há mais tempo que o limite configurado (minutos), **quando**
  `get()` é chamado, **então** retorna `None` (expirado) — força a camada seguinte a ser
  consultada.
- **Dado** o cache de memória no limite de tamanho configurado, **quando** um novo schema é
  inserido, **então** o item menos recentemente usado é removido (política LRU) — o cache
  nunca cresce sem limite, mesmo sendo um cenário improvável neste domínio.

### 3.2 `SchemaCacheRepository` (Postgres, tabela `schema_cache`)

```python
class SchemaCacheRepository(Protocol):
    async def get(self, entity_type: EntityType) -> CachedSchemaRow | None: ...
    async def save(self, entity_type: EntityType, content: dict, etag: str,
                    fetched_at: datetime) -> None: ...
    async def touch_last_checked(self, entity_type: EntityType) -> None: ...
```

**Casos de teste (integração, com banco real via testcontainers):**
- **Dado** nenhuma linha para `entity_type="Streetlight"`, **quando** `get()` é chamado,
  **então** retorna `None`.
- **Dado** `save()` chamado duas vezes para o mesmo `entity_type` com conteúdos diferentes,
  **quando** `get()` é chamado, **então** retorna o conteúdo da segunda chamada (upsert por
  `entity_type`, não duplica linha).
- **Dado** dois processos (`worker`) chamando `save()` para o mesmo `entity_type`
  simultaneamente, **quando** ambos terminam, **então** a tabela não fica em estado
  inconsistente (constraint de unicidade em `entity_type` + operação atômica —
  este é o teste que comprova o motivo real de usar banco em vez de só memória: cache
  compartilhado entre workers da fila, seção 1.2/3.6 do plano geral).

### 3.3 `ConditionalSchemaFetcher` — verificação via ETag

```python
class ConditionalSchemaFetcher:
    async def fetch(self, schema_url: str, known_etag: str | None) -> FetchResult:
        """Retorna NotModified() se known_etag ainda é válido (HTTP 304),
        ou NewContent(content, etag) se mudou ou known_etag era None."""
```

**Casos de teste:**
- **Dado** `known_etag=None` (primeira busca), **quando** `fetch()` é chamado, **então**
  retorna `NewContent` com o conteúdo e o `etag` da resposta.
- **Dado** `known_etag` igual ao atual da fonte, **quando** `fetch()` é chamado, **então**
  retorna `NotModified` — sem corpo de resposta processado.
- **Dado** `known_etag` diferente do atual (schema mudou na fonte), **quando** `fetch()` é
  chamado, **então** retorna `NewContent` com o conteúdo novo e o `etag` atualizado.
- **Dado** timeout ou erro de rede durante a requisição, **quando** `fetch()` é chamado,
  **então** levanta `SchemaFetchUnavailableError` (erro tipado, não uma exceção genérica) —
  permite ao adaptador decidir explicitamente cair para o cache, em vez de mascarar o tipo
  de falha.

### 3.4 `SmartDataModelsAdapter.fetch_schema` — orquestração da política completa

Implementa a política de 6 passos da seção 3.3 do plano geral. Casos de teste de
integração, combinando os componentes acima (com mocks dos componentes de rede):

- **Dado** o schema presente e válido na camada de memória, **quando** `fetch_schema()` é
  chamado, **então** retorna direto da memória — `SchemaCacheRepository.get()` e
  `ConditionalSchemaFetcher.fetch()` **não são chamados** (comprova que a camada de memória
  realmente evita as camadas mais caras).
- **Dado** ausente da memória mas presente no banco, e a verificação condicional retorna
  `NotModified`, **quando** `fetch_schema()` é chamado, **então** retorna o conteúdo do
  banco com `origin=SchemaOrigin(LIVE, ...)` (confirmado atual, mesmo vindo do banco) e
  `touch_last_checked()` é chamado.
- **Dado** ausente da memória, presente no banco, mas a verificação condicional retorna
  `NewContent` (mudou), **quando** `fetch_schema()` é chamado, **então** o novo conteúdo é
  salvo no banco (`save()` chamado com o novo `etag`) e retornado com
  `origin=SchemaOrigin(LIVE, ...)`.
- **Dado** ausente de todas as camadas, com rede disponível, **quando** `fetch_schema()` é
  chamado, **então** busca do zero, salva no banco, retorna com `origin=LIVE`.
- **Dado** presente no banco, mas a verificação condicional levanta
  `SchemaFetchUnavailableError` (rede indisponível), **quando** `fetch_schema()` é chamado,
  **então** retorna o conteúdo do banco com `origin=SchemaOrigin(CACHE, fetched_at=<data do
  banco>)` — **nunca** `LIVE` nesse caso, mesmo que o conteúdo seja idêntico ao atual por
  coincidência; a auditoria precisa registrar que não foi possível confirmar.
- **Dado** ausente de todas as camadas **e** rede indisponível, **quando** `fetch_schema()`
  é chamado, **então** levanta `SchemaUnavailableError` — a `Application` layer converte
  isso em `EntityReport` com... **nota importante**: isso é diferente de
  `NO_MODEL_FOUND` (Fase 1). `NO_MODEL_FOUND` significa "catálogo confirma que não existe
  modelo para este tipo". Este caso significa "existe modelo, mas não foi possível obter o
  conteúdo agora" — precisa de um terceiro estado ou de um relatório de erro específico,
  não deve ser confundido com nenhum dos dois casos anteriores. Ver ajuste necessário na
  Fase 1 (seção 5, abaixo).

---

## 4. Ajuste retroativo necessário na Fase 1

Ao especificar a Fase 2 em detalhe, ficou evidente uma lacuna na Fase 1:
`ConformanceStatus` não distingue "não existe modelo" (`NO_MODEL_FOUND`) de "existe modelo,
mas não foi possível obter o schema agora" (rede indisponível e sem cache algum). São
situações diferentes — a primeira é definitiva, a segunda é transitória e deveria permitir
nova tentativa depois. Ajuste proposto antes de a Fase 2 ser implementada:

```python
class ConformanceStatus(StrEnum):
    CONFORMANT = "conformant"
    PARTIAL = "partial"
    NON_CONFORMANT = "non_conformant"
    NO_MODEL_FOUND = "no_model_found"        # catálogo confirma: não existe
    SCHEMA_UNAVAILABLE = "schema_unavailable"  # existe, mas não obtido agora
```

**Novo caso de teste a adicionar retroativamente na suíte da Fase 1:**
- Dado `data_model` presente (não `None`) mas nenhum conteúdo de schema obtido, quando se
  constrói um `EntityReport`, então `status` deve ser `SCHEMA_UNAVAILABLE`, distinto de
  `NO_MODEL_FOUND`.

Esse é exatamente o tipo de ajuste que a prática de especificar fase por fase antes de
implementar existe para capturar cedo — corrigir aqui custa uma linha de enum; corrigir
depois de implementado custaria revisar toda a lógica de `RunAuditUseCase`.

---

## 5. Definição de pronto da Fase 2

- Todos os casos de teste acima implementados e passando.
- `CatalogIndex` testado sem rede (usa o catálogo empacotado da biblioteca).
- `SmartDataModelsAdapter.fetch_schema` testado com testcontainers (Postgres real) +
  mocks da camada HTTP — nenhum teste desta fase depende do GitHub estar no ar.
- O ajuste da seção 4 aplicado retroativamente à suíte da Fase 1, com o novo caso de teste
  passando antes de a Fase 2 ser considerada concluída.