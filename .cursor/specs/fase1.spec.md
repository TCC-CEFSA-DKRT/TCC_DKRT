# Specs — Fase 1: Domínio e StructuralValidator

Especificação pronta para TDD: cada componente tem contrato (assinatura) e lista de casos de
teste no formato dado/quando/então. A prática recomendada é escrever estes testes primeiro
(como stubs `pytest` que falham), depois implementar até todos passarem.

**Nota sobre os exemplos de `Streetlight`:** os atributos usados abaixo
(`location`, `illuminanceLevel`, `lanternHeight`, `areaServed`, `refStreetlightModel`,
`dateCreated`, `dateModified`) são confirmados no `spec.md` oficial do domínio
Streetlighting. A lista definitiva de propriedades obrigatórias (`required`) deve vir do
`schema.json` ao vivo em tempo de implementação (via `SchemaCatalogPort`) — não é fixada
aqui. Os testes abaixo usam esses atributos como exemplo representativo do formato NGSI-v2 e
das regras do `StructuralValidator`, não como transcrição completa e definitiva do schema.

---

## 1. Value Objects

### 1.1 `ConformanceStatus`

```python
class ConformanceStatus(StrEnum):
    CONFORMANT = "conformant"
    PARTIAL = "partial"              # violações apenas de severidade WARNING/INFO
    NON_CONFORMANT = "non_conformant"  # ao menos uma violação de severidade ERROR
    NO_MODEL_FOUND = "no_model_found"  # entity_type sem Smart Data Model correspondente
```

**Casos de teste:**
- Dado uma lista de violações vazia, quando se deriva o status, então o resultado é `CONFORMANT`.
- Dado uma lista só com violações `WARNING`, quando se deriva o status, então o resultado é `PARTIAL`.
- Dado uma lista com ao menos uma violação `ERROR` (mesmo com outras `WARNING`/`INFO` juntas), quando se deriva o status, então o resultado é `NON_CONFORMANT`.
- Dado que nenhum modelo foi encontrado para o `entity_type`, quando se deriva o status, então o resultado é `NO_MODEL_FOUND`, independentemente de haver ou não violações.

### 1.2 `Tenant`

```python
@dataclass(frozen=True)
class Tenant:
    fiware_service: str
    fiware_service_path: str = "/"
```

**Casos de teste:**
- Dado `fiware_service` vazio, quando se constrói um `Tenant`, então uma exceção de domínio é levantada (tenant é obrigatório para toda auditoria — isolamento multi-tenant não é opcional).
- Dado `fiware_service_path` omitido, quando se constrói um `Tenant`, então o valor padrão é `"/"`.
- Dois `Tenant` com os mesmos valores são iguais entre si (`frozen=True` + `dataclass` já garante isso — teste serve como documentação executável do contrato).

### 1.3 `EntityType`

```python
@dataclass(frozen=True)
class EntityType:
    value: str  # ex.: "Streetlight"
```

**Casos de teste:**
- Dado uma string vazia, quando se constrói um `EntityType`, então uma exceção de domínio é levantada.
- Dado `"streetlight"` (minúsculo), quando se constrói um `EntityType`, então o valor é preservado exatamente como informado — **não normaliza capitalização** (tipos NGSI são case-sensitive; normalizar silenciosamente esconderia um erro real do cliente).

### 1.4 `DataModelRef`

```python
@dataclass(frozen=True)
class DataModelRef:
    subject: str          # ex.: "dataModel.Streetlighting"
    model_name: str       # ex.: "Streetlight"
    version: str
    schema_url: str
```

Sem lógica própria além de armazenamento — casos de teste cobrem só construção com campos obrigatórios ausentes (mesma regra dos anteriores).

---

## 2. Entidades

### 2.1 `Violation`

```python
class ViolationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class DetectionSource(StrEnum):
    STRUCTURAL = "structural"   # Nível 1
    SEMANTIC = "semantic"       # Nível 2 (Fase 7, fora do escopo desta fase)

@dataclass(frozen=True)
class Violation:
    attribute_path: str
    severity: ViolationSeverity
    rule: str
    expected: str | None
    found: str | None
    message: str
    detected_by: DetectionSource
```

**Casos de teste:**
- Dado uma instância de `Violation`, quando se tenta reatribuir um campo, então uma exceção é levantada (imutabilidade — `frozen=True`).
- Dado `attribute_path="location"` e `attribute_path="address.streetName"`, quando ambos são construídos, então os dois são aceitos (caminho simples e caminho aninhado com `.`).

### 2.2 `EntityReport`

```python
class SchemaSource(StrEnum):
    LIVE = "live"
    CACHE = "cache"

@dataclass(frozen=True)
class SchemaOrigin:
    source: SchemaSource
    fetched_at: datetime

@dataclass
class EntityReport:
    entity_id: str
    entity_type: EntityType
    data_model: DataModelRef | None
    status: ConformanceStatus
    violations: list[Violation]
    recommendations: list["Recommendation"]
    schema_origin: SchemaOrigin | None   # None quando status == NO_MODEL_FOUND
    semantic_analysis_skipped: bool
    analyzed_at: datetime
```

**Casos de teste:**
- Dado `data_model=None`, quando se constrói um `EntityReport`, então `status` deve ser `NO_MODEL_FOUND` — uma exceção de domínio é levantada se `data_model=None` e `status` for qualquer outro valor (invariante: os dois campos não podem se contradizer).
- Dado `status=CONFORMANT`, quando se constrói um `EntityReport` com `violations` não vazia contendo severidade `ERROR`, então uma exceção de domínio é levantada (mesma lógica de invariante — o status precisa ser consistente com as violações, a entidade não decide isso livremente, é derivado).
- Dado um relatório com `schema_origin.source == CACHE`, quando o relatório é serializado/representado, então a informação de que veio de cache é preservada e visível (honestidade metodológica — não pode se perder na composição do relatório final).

### 2.3 `Recommendation`

```python
class RecommendationAction(StrEnum):
    RENAME_ATTRIBUTE = "rename_attribute"
    ADD_MISSING_ATTRIBUTE = "add_missing_attribute"
    FIX_TYPE = "fix_type"
    FIX_FORMAT = "fix_format"

@dataclass(frozen=True)
class Recommendation:
    attribute_path: str
    action: RecommendationAction
    proposed_patch: dict          # ex.: {"from": "temp", "to": "temperature"}
    rationale: str
    confidence: float             # 0.0–1.0
```

**Casos de teste:**
- Dado `confidence=1.5` ou `confidence=-0.1`, quando se constrói uma `Recommendation`, então uma exceção de domínio é levantada (fora do intervalo válido).
- Dado `proposed_patch={}` (vazio), quando se constrói uma `Recommendation`, então uma exceção de domínio é levantada — uma recomendação sem patch estruturado não serve ao propósito de ser consumida pelo Nível 3 no futuro.

### 2.4 `AuditRun`

```python
class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

@dataclass
class RunSummary:
    total_entities: int
    conformant_count: int
    non_conformant_count: int
    partial_count: int
    no_model_count: int

    def __post_init__(self) -> None:
        # invariante: os quatro contadores somam o total
        ...

@dataclass
class AuditRun:
    id: UUID
    tenant: Tenant
    entity_type: EntityType | None   # None = todos os tipos do tenant
    status: RunStatus
    reports: list[EntityReport]
    summary: RunSummary
    started_at: datetime
    finished_at: datetime | None
    broker_url: str
```

**Casos de teste:**
- Dado um `RunSummary` cujos contadores não somam `total_entities`, quando se constrói, então uma exceção de domínio é levantada.
- Dado um `AuditRun` com `status=COMPLETED`, quando se verifica `finished_at`, então não pode ser `None` (invariante: todo run concluído tem timestamp de fim).
- Dado um `AuditRun` recém-criado (`status=QUEUED`), quando se verifica `reports`, então a lista é vazia e `finished_at` é `None`.
- Dado um método `AuditRun.add_report(report)`, quando chamado múltiplas vezes, então `summary` é recalculado automaticamente a cada chamada (o agregado nunca fica dessincronizado da lista de relatórios — não é responsabilidade de quem chama manter isso manualmente).

---

## 3. `StructuralValidator` (Nível 1)

```python
class StructuralValidator:
    def validate(self, entity: dict, schema: dict) -> list[Violation]:
        """Compara uma entidade NGSI-v2 (formato keyValues, já normalizada pelo
        ngsi_v2_mapper) contra um Smart Data Model schema.json. Não faz nenhuma
        chamada de rede, não decide status — só produz violações."""
```

Pré-condição documentada no contrato: `entity` já passou pelo `ngsi_v2_mapper` (converteu do
envelope NGSI-v2, onde cada atributo é `{"type": ..., "value": ...}`, para um dict plano de
valores) antes de chegar aqui. O `StructuralValidator` nunca lida com o envelope NGSI
diretamente — essa responsabilidade é do mapper (módulo isolado, ver Parte II do plano),
justamente porque misturar as duas coisas foi identificado como o detalhe mais fácil de errar
nesta implementação.

### 3.1 Casos de teste — propriedade obrigatória

- **Dado** um schema com `"required": ["id", "type", "location"]` e uma entidade sem o
  campo `location`, **quando** `validate()` é chamado, **então** o resultado contém uma
  `Violation` com `rule="required_property_missing"`, `attribute_path="location"`,
  `severity=ERROR`, `detected_by=STRUCTURAL`.
- **Dado** uma entidade com todos os campos obrigatórios presentes, **quando** `validate()`
  é chamado, **então** nenhuma violação de `required_property_missing` é produzida.
- **Dado** um schema onde `location` é obrigatório apenas se `address` estiver ausente
  (requisito condicional, real neste modelo — confirmado no `spec.md`), **quando** a
  entidade tem `address` mas não `location`, **então** nenhuma violação é produzida para
  `location` (a implementação do validador precisa suportar essa condicionalidade —
  registrar como caso de teste explícito evita que passe despercebido).

### 3.2 Casos de teste — tipo incompatível

- **Dado** `illuminanceLevel` definido no schema como `number` e uma entidade onde
  `illuminanceLevel` é a string `"0.8"` (em vez do número `0.8`), **quando** `validate()` é
  chamado, **então** o resultado contém uma `Violation` com `rule="type_mismatch"`,
  `expected="number"`, `found="string"`, `severity=ERROR`.
- **Dado** `illuminanceLevel` como número dentro do schema mas fora do intervalo permitido
  (schema define `minimum: 0, maximum: 1`; entidade tem `illuminanceLevel=1.5`), **quando**
  `validate()` é chamado, **então** o resultado contém uma `Violation` com
  `rule="value_out_of_range"`, `severity=ERROR`.

### 3.3 Casos de teste — formato

- **Dado** `dateModified` definido no schema com `"format": "date-time"` e uma entidade com
  `dateModified="ontem"`, **quando** `validate()` é chamado, **então** o resultado contém
  uma `Violation` com `rule="format_invalid"`, `expected="date-time"`, `severity=ERROR`.
- **Dado** `dateModified="2026-08-15T10:00:00Z"` (ISO 8601 válido), **quando** `validate()`
  é chamado, **então** nenhuma violação de formato é produzida para esse campo.

### 3.4 Casos de teste — enum

- **Dado** um atributo com `"enum": ["steel", "aluminium", "wood", "other"]` no schema e uma
  entidade com valor `"iron"`, **quando** `validate()` é chamado, **então** o resultado
  contém uma `Violation` com `rule="enum_violation"`, `severity=ERROR`, listando os valores
  permitidos em `expected`.

### 3.5 Casos de teste — propriedade fora do schema (`additionalProperties`)

Este é o caso mais importante para a Fase 7 (Nível 2) — marca candidatos a análise semântica.

- **Dado** um schema com `"additionalProperties": false` e uma entidade contendo o atributo
  `temp` (que não existe no schema — o nome correto seria `temperature`), **quando**
  `validate()` é chamado, **então** o resultado contém uma `Violation` com
  `rule="unexpected_property"`, `severity=WARNING` (não `ERROR` — é candidato a
  investigação semântica, não uma quebra estrutural certa), `detected_by=STRUCTURAL`.
- **Dado** o mesmo cenário acima, **quando** o relatório é montado, **então**
  `semantic_analysis_skipped=False` para essa entidade (a presença de uma violação
  `WARNING` de `unexpected_property` é justamente o sinal que aciona o Nível 2 na Fase 7 —
  este teste documenta o contrato entre as duas fases, mesmo a Fase 7 ainda não existindo).

### 3.6 Casos de teste — entidade totalmente conforme

- **Dado** uma entidade `Streetlight` com `id`, `type="Streetlight"`, `location` válido,
  `illuminanceLevel=0.8`, `lanternHeight=6.5`, `dateCreated` e `dateModified` em formato
  válido, e nenhum atributo fora do schema, **quando** `validate()` é chamado, **então** o
  resultado é uma lista vazia.

### 3.7 Casos de teste — múltiplas violações simultâneas

- **Dado** uma entidade com propriedade obrigatória ausente **e** um tipo incompatível em
  outro campo **e** um atributo fora do schema, **quando** `validate()` é chamado, **então**
  o resultado contém as três violações, cada uma com o `rule`/`severity`/`attribute_path`
  corretos — o validador não para na primeira violação encontrada (relatório precisa ser
  completo, não apenas apontar o primeiro problema).

---

## 4. Fixtures de referência

Três entidades fixas, usadas em todos os testes acima e reaproveitadas na Fase 10
(experimento). Ficam em `tests/fixtures/entities/streetlight_*.json`.

- `streetlight_conformant.json` — entidade completa, todos os tipos e formatos corretos, sem atributos extras.
- `streetlight_partial.json` — estruturalmente válida (todos os obrigatórios presentes, tipos corretos), mas com o atributo `temp` em vez de `temperature` — dispara `WARNING`/`unexpected_property`, status `PARTIAL`.
- `streetlight_non_conformant.json` — falta `location` **e** não tem `address`, `illuminanceLevel` como string — dispara dois `ERROR`, status `NON_CONFORMANT`.

---

## 5. Definição de pronto da Fase 1

- Todos os casos de teste acima implementados como testes `pytest`, passando.
- Cobertura de `domain/` acima de 90%.
- Nenhum teste desta fase depende de rede, banco ou processo externo — suíte inteira roda
  em menos de 2 segundos.
- Teste de arquitetura (seção 6.4 do plano geral) já ativo: falha o CI se `domain/`
  importar qualquer coisa fora da biblioteca padrão do Python.