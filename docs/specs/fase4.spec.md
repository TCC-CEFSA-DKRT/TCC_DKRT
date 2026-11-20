# Specs — Fase 4: Nível 1 Ponta a Ponta

Primeira fase que integra tudo (Fases 1–3) num fluxo real: Orion → validação estrutural →
persistência → API/CLI. **Ainda sem fila** (Fase 5) e **sem SLM** (Fase 7) — a auditoria
roda de forma síncrona/in-process nesta fase. O contrato da API já é desenhado para não
mudar quando a fila for introduzida — só o mecanismo interno de execução muda depois.

---

## 1. `NgsiV2Mapper` — o detalhe mais fácil de errar (plano geral, seção 3.2)

```python
class NgsiV2Mapper:
    def to_plain_values(self, raw_entity: dict) -> dict:
        """Converte o envelope NGSI-v2 normalizado ({"attr": {"type":...,
        "value":...,"metadata":{...}}}) para um dict plano de valores. `id` e
        `type` da entidade não são envelopados pelo NGSI e são preservados
        como estão. Só remove UM nível de envelope — não desce recursivamente
        dentro do próprio valor (ex.: um GeoProperty com estrutura GeoJSON
        aninhada permanece intacto)."""
```

### 1.1 Casos de teste

- **Dado** uma entidade NGSI-v2 normalizada com `illuminanceLevel: {"type": "Number",
  "value": 0.8, "metadata": {}}`, **quando** `to_plain_values()` é chamado, **então** o
  resultado tem `illuminanceLevel: 0.8` (valor extraído, envelope removido).
- **Dado** `location: {"type": "geo:json", "value": {"type": "Point", "coordinates": [-3.7,
  40.4]}, "metadata": {}}`, **quando** mapeado, **então** o resultado tem `location:
  {"type": "Point", "coordinates": [-3.7, 40.4]}` — o valor geoespacial interno **não** é
  desembrulhado de novo (só um nível de envelope NGSI é removido, o `type`/`coordinates` de
  dentro do GeoJSON não são atributos NGSI, são a estrutura do próprio dado geoespacial).
- **Dado** os campos `id` e `type` da entidade (não envelopados pelo NGSI-v2), **quando**
  mapeado, **então** aparecem no resultado exatamente como vieram, sem tentativa de
  desembrulhar.
- **Dado** um atributo malformado, sem a chave `"value"` (resposta inesperada do broker),
  **quando** mapeado, **então** levanta `MalformedAttributeError` nomeando o atributo — não
  `KeyError` genérico, e não interrompe silenciosamente perdendo o dado.
- **Dado** uma entidade com metadados no atributo (ex.: `timestamp` dentro de
  `metadata`), **quando** mapeada para `to_plain_values()`, **então** os metadados **não**
  aparecem no dict plano (esse método serve só à validação estrutural) — mas o `RawEntity`
  original (não mapeado) continua disponível em paralelo no `RunAuditUseCase`, preservado
  para uso futuro do Nível 2 (Fase 7), que pode precisar de metadados como `timestamp`.

---

## 2. `OrionAdapter` (implementa `ContextBrokerPort`)

```python
# domain/ports/context_broker_port.py
class ContextBrokerPort(Protocol):
    async def fetch_entities(self, tenant: Tenant, entity_type: EntityType | None,
                              entity_id: str | None = None) -> list[RawEntity]: ...
```

### 2.1 Casos de teste (integração, contra Orion real via testcontainers/docker-compose)

- **Dado** um Orion com 3 entidades do tipo `Streetlight` sob o tenant configurado,
  **quando** `fetch_entities(tenant, EntityType("Streetlight"))` é chamado, **então**
  retorna as 3 entidades, cada uma em formato NGSI-v2 normalizado.
- **Dado** o mesmo Orion, **quando** `fetch_entities(tenant, entity_type=None)` é chamado,
  **então** retorna entidades de **todos** os tipos existentes sob aquele tenant (auditoria
  ampla, seção "granularidade" do plano de aplicação).
- **Dado** `entity_id` informado além de `entity_type`, **quando** chamado, **então** filtra
  para aquela entidade específica (granularidade "uma entidade só").
- **Dado** um tenant sem nenhuma entidade daquele tipo, **quando** chamado, **então**
  retorna lista vazia — não é erro.
- **Dado** o Orion inacessível (rede/serviço fora do ar), **quando** chamado, **então**
  levanta `ContextBrokerUnavailableError` (erro tipado — permite ao caso de uso decidir
  explicitamente marcar o run como `FAILED`, em vez de deixar uma exceção genérica
  propagar sem contexto).
- **Dado** os headers `Fiware-Service`/`Fiware-ServicePath` do `Tenant`, **quando** qualquer
  chamada é feita, **então** são enviados exatamente como especificado no tenant — nunca um
  valor padrão silencioso que vazaria dado de um tenant errado.

---

## 3. `RunAuditUseCase` — orquestração

```python
class RunAuditUseCase:
    def __init__(self, context_broker: ContextBrokerPort,
                 schema_catalog: SchemaCatalogPort,
                 validator: StructuralValidator,
                 mapper: NgsiV2Mapper,
                 uow: UnitOfWork): ...

    async def execute(self, tenant: Tenant, entity_type: EntityType | None = None,
                       entity_id: str | None = None) -> UUID:
        """Cria o run, processa cada entidade encontrada, retorna o run_id
        imediatamente após criar o run — o processamento em si pode
        continuar (nesta fase, síncrono; na Fase 5, via worker)."""
```

### 3.1 Casos de teste — caminho feliz

- **Dado** o Orion retornando 3 entidades conformes, **quando** `execute()` roda até o fim,
  **então** o run criado tem `status=COMPLETED`, `summary.total_entities=3`,
  `summary.conformant_count=3`, e 3 `EntityReport` persistidos.
- **Dado** uma mistura de entidades conformes, parcialmente conformes e não conformes,
  **quando** `execute()` roda, **então** `summary` reflete a contagem exata de cada
  categoria, consistente com o invariante de domínio já testado na Fase 1.

### 3.2 Casos de teste — resiliência (uma entidade ruim não derruba o lote)

- **Dado** um lote de 10 entidades onde 1 tem atributo malformado (dispara
  `MalformedAttributeError` no mapper), **quando** `execute()` roda, **então** as outras 9
  são processadas normalmente, e a entidade problemática recebe um `EntityReport` próprio
  registrando a falha de mapeamento como uma violação (`rule="malformed_attribute"`,
  `severity=ERROR`) — **o run inteiro não falha por causa de uma entidade**.
- **Dado** o catálogo (`SchemaCatalogPort`) sem modelo para o tipo da entidade, **quando**
  `execute()` roda, **então** o `EntityReport` daquela entidade tem
  `status=NO_MODEL_FOUND` (Fase 1) e o run **completa normalmente** — não é falha do caso
  de uso, é resultado válido de auditoria.
- **Dado** o catálogo retornando erro de indisponibilidade de schema
  (`SchemaUnavailableError`, achado da Fase 2) para uma entidade específica, **quando**
  `execute()` roda, **então** aquela entidade recebe `status=SCHEMA_UNAVAILABLE`, e as
  demais entidades (de tipos com schema disponível) continuam normalmente.

### 3.3 Casos de teste — falha de infraestrutura (diferente de resultado de auditoria)

- **Dado** `ContextBrokerPort.fetch_entities` levantando
  `ContextBrokerUnavailableError` **antes** de qualquer entidade ser obtida, **quando**
  `execute()` roda, **então** o run é marcado `status=FAILED` com o motivo registrado — essa
  é uma falha de infraestrutura, diferente de `NO_MODEL_FOUND`/`SCHEMA_UNAVAILABLE`
  (que são resultados válidos por entidade).
- **Dado** a conexão com o Orion cair **no meio** do processamento (após 5 de 10 entidades),
  **quando** `execute()` roda, **então** o run é marcado `status=PARTIAL` — os 5 relatórios
  já processados permanecem persistidos e consultáveis, não descartados.

---

## 4. API REST (FastAPI)

### 4.1 `POST /audits`

```
POST /audits
{"entity_type": "Streetlight", "entity_id": null}
→ 202 Accepted
{"run_id": "...", "status": "queued"}
```

**Decisão de design:** o contrato retorna `202 Accepted` com `run_id` **desde já**, mesmo
a execução sendo síncrona internamente nesta fase — para que a Fase 5 (fila real) não exija
mudança de contrato para quem consome a API, só troca o mecanismo interno.

### 4.2 Casos de teste

- **Dado** um corpo de requisição válido, **quando** `POST /audits` é chamado, **então**
  retorna `202` com um `run_id` válido (UUID).
- **Dado** um corpo sem `entity_type` nem `entity_id` (auditoria ampla), **quando**
  chamado, **então** aceita normalmente (granularidade "tudo" é válida).
- **Dado** ausência de identificação de tenant na requisição (nenhum header/token — auth
  completa é escopo de fase posterior), **quando** chamado, **então** retorna `401`/`403` —
  **nunca** processa uma auditoria sem tenant identificado, mesmo antes da autenticação
  completa existir; um stub mínimo de identificação (ex.: header obrigatório) já entra
  nesta fase, não é adiado.

### 4.3 `GET /audits/{run_id}`

- **Dado** um run existente pertencente ao tenant da requisição, **quando** `GET
  /audits/{run_id}` é chamado, **então** retorna `200` com o run completo (status, summary,
  relatórios).
- **Dado** um `run_id` que existe mas pertence a **outro** tenant, **quando** chamado,
  **então** retorna `404` — nunca `403` (que confirmaria a existência do recurso para quem
  não deveria nem saber que ele existe; teste que espelha o isolamento de tenant já validado
  na Fase 3, agora na borda HTTP).

### 4.4 `GET /health/live` e `GET /health/ready`

- **Dado** a aplicação rodando, **quando** `GET /health/live` é chamado, **então** retorna
  `200` sempre que o processo está de pé (não verifica dependências externas).
- **Dado** o banco de dados inacessível, **quando** `GET /health/ready` é chamado, **então**
  retorna `503`, distinguindo "processo vivo" de "pronto para tráfego" — usado por
  orquestradores de deploy para decidir se envia tráfego à instância.

---

## 5. CLI

```
audit run --tenant openiot --entity-type Streetlight
audit run --tenant openiot --entity-type Streetlight --entity-id urn:ngsi-ld:Streetlight:001
audit status --run-id <uuid>
```

### 5.1 Casos de teste

- **Dado** `audit run` executado com sucesso, **quando** o comando termina, **então** imprime
  o `run_id` e um resumo do status final.
- **Dado** `audit status --run-id <uuid inexistente>`, **quando** executado, **então**
  retorna código de saída diferente de zero e mensagem clara — nunca um traceback Python cru
  na tela do usuário final.

---

## 6. Definição de pronto da Fase 4

- `POST /audits` audita um tipo real contra um Orion de desenvolvimento (docker-compose) e
  `GET /audits/{run_id}` mostra o resultado persistido — **critério do plano geral,
  literal**.
- Todos os casos de teste acima passando, incluindo os de resiliência (entidade ruim não
  derruba o lote) e isolamento de tenant na borda HTTP.
- CLI e API chamam o **mesmo** `RunAuditUseCase` — nenhuma lógica de auditoria duplicada
  entre as duas interfaces.
- Esta é a primeira entrega demonstrável ao orientador, conforme o roteiro geral.