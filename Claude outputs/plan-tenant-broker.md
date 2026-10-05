# Plano TDD: o modo SaaS passa a auditar o broker do próprio cliente

A causa confirmada está em `container.py`, nas linhas 101-102 e 197. As duas leem `Settings.fiware_broker_url`, que é um valor global. Isso acontece em todos os caminhos: a API (`POST /audits`, `GET /entity-types`), o worker em background (`app.py:105`), o worker do EC2 (`worker/main.py:148`), os dois Lambdas e a CLI. Em modo SaaS, o JWT identifica o tenant, mas essa informação nunca chega à escolha de qual broker consultar.

## 0. Fatos confirmados no código

- **`ContextBrokerPort`** (`domain/ports/context_broker_port.py`) tem dois métodos: `fetch_entities(tenant, entity_type, entity_id=None)` e `list_entity_types(tenant)`. Os dois já recebem o `Tenant` em cada chamada. Isso permite rotear por chamada sem nenhuma informação de HTTP ou JWT.
- **`OrionAdapter.__init__(self, base_url: str, client: httpx.AsyncClient | None = None)`** guarda `base_url.rstrip("/")`. Os headers são montados duas vezes (em `fetch_entities` e em `list_entity_types`) e contêm só `Fiware-Service`/`Fiware-ServicePath`. As mensagens de erro incluem `exc.request.url`. O adapter não guarda nenhum estado mutável além de `_base_url` e `_client`.
- **`RunAuditUseCase.__init__(..., *, broker_url: str, ...)`** usa `self._broker_url` só em `create_run()`, dentro de `AuditRun.create(..., broker_url=...)`. `process()` não captura nada (propaga para o worker chamar `nack`). `process_run()` captura só `ContextBrokerUnavailableError`.
- **O worker não tem contexto HTTP.** `AuditWorker._process_one` chama `process(job.run_id, job.tenant, ...)`, e `worker_handler._handle_async` faz o mesmo a partir de `parse_audit_job(record["body"])`. O `AuditJob` (serializado no SQS) carrega só `run_id`, os dois campos do tenant, `entity_type`, `entity_id` e `enqueued_at`. Não há JWT, URL nem chave. `get_run_audit_use_case()` é chamado **uma vez** no lifespan e no `worker/main.py`, e uma vez por invocação no Lambda. Essa única instância processa jobs de **qualquer** tenant.
- **`TenantAccountRepository.get_by_tenant(tenant) -> TenantAccount | None`** consulta pela PK composta `(fiware_service, fiware_service_path)` e já devolve `broker_api_key` decifrada (MultiFernet). `broker_url` é NOT NULL, com `CHECK <> ''`. Na prática, "broker não configurado" significa "a linha não existe".
- **`get_tenant_account_repository()`** levanta `RuntimeError` quando `BROKER_API_KEY_ENCRYPTION_KEYS` está ausente. Hoje o modo self-hosted **não** chama essa factory, e isso precisa continuar assim.
- **`get_http_client()`** é um único `httpx.AsyncClient()` compartilhado (Ollama, schemas e Orion). Verifiquei empiricamente no httpx 0.28.1 instalado:
  - o cliente padrão guarda o `Set-Cookie` e o **reenvia** na próxima chamada ao mesmo host (`[None, 'sess=A']`);
  - `cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))` bloqueia os cookies (`[None, None]`);
  - `follow_redirects` é `False` por padrão, e `raise_for_status()` levanta erro em respostas 3xx.
- **Testes de REST** fazem override com `app.dependency_overrides[get_context_broker]` (`test_entity_types_router.py`, `test_auth.py`). Por isso `get_context_broker` precisa continuar sendo um callable sem argumentos obrigatórios.
- **Testes de arquitetura:** `test_architecture.py` exige que `domain/` importe só a stdlib. `RunAuditUseCase` é construído só em `container.py` e em `test_run_audit_use_case.py::_make_use_case` (linha 271).
- **ADR-0019 §1** já registrava a intenção: "`OrionAdapter.__init__` ganha um parâmetro opcional `api_key`… `container.get_context_broker()` resolve `broker_url`/`broker_api_key` a partir da conta autenticada; sem tenant autenticado (self-hosted), cai para `Settings.fiware_broker_url`".

## 1. `container.get_context_broker()`: decisão por modo

A escolha é feita pelo modo de implantação, e o roteamento por tenant acontece dentro do adapter.

```python
@lru_cache
def get_broker_http_client() -> httpx.AsyncClient:
    # Cliente exclusivo para brokers de tenants (SaaS): sem cookie jar e sem redirect.
    return httpx.AsyncClient(
        cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        follow_redirects=False,
    )

def get_context_broker() -> ContextBrokerPort:
    settings = get_settings()
    if settings.deployment_mode == "saas":
        return TenantRoutedContextBroker(get_tenant_account_repository(), client=get_broker_http_client())
    return OrionAdapter(settings.fiware_broker_url, client=get_http_client())
```

- **Self-hosted fica byte-idêntico.** O ramo `selfhosted` é exatamente a linha atual: mesma URL, mesmo cliente compartilhado, sem `api_key` e sem tocar em `get_tenant_account_repository()`. Continua funcionando sem `BROKER_API_KEY_ENCRYPTION_KEYS`.
- **SaaS falha cedo** se as chaves de criptografia faltarem: o `RuntimeError` já existente aparece no startup do worker, que chama `get_run_audit_use_case()`.
- **O use case perde o parâmetro `broker_url=`** no construtor (ver seção 6).
- **Não adotei a alternativa de resolver o broker em uma dependência FastAPI** a partir do JWT (por exemplo, `get_context_broker(tenant=Depends(get_tenant))`). Ela só funcionaria no caminho HTTP. O worker, o Lambda e a CLI não têm JWT, e a instância única do use case atende todos os tenants. Portanto a resolução precisa ser por chamada e ter o `Tenant` como chave, e o lugar natural para isso é o adapter.

## 2. `TenantRoutedContextBroker`: consulta em cada chamada, sem cache

Novo arquivo: `src/auditor/infrastructure/context_broker/tenant_routed_context_broker.py`.

```python
class TenantRoutedContextBroker(ContextBrokerPort):
    def __init__(self, accounts: TenantAccountRepository, client: httpx.AsyncClient) -> None: ...

    async def _adapter_for(self, tenant: Tenant) -> OrionAdapter:
        account = await self._accounts.get_by_tenant(tenant)
        if account is None:
            raise TenantBrokerNotConfiguredError(tenant)
        return OrionAdapter(account.broker_url, client=self._client, api_key=account.broker_api_key)

    async def fetch_entities(self, tenant, entity_type, entity_id=None):
        return await (await self._adapter_for(tenant)).fetch_entities(tenant, entity_type, entity_id)

    async def list_entity_types(self, tenant):
        return await (await self._adapter_for(tenant)).list_entity_types(tenant)

    async def broker_url(self, tenant):
        return await (await self._adapter_for(tenant)).broker_url(tenant)
```

- **Isolamento pela forma do código.** Um único argumento `tenant` decide a URL, a chave e os headers `Fiware-*`. O `OrionAdapter` é criado **por chamada**, como variável local. A classe não guarda nenhum atributo com "a conta atual", então não há estado mutável que duas corrotinas possam disputar.
- **Não criei uma nova interface para o repositório.** Depender de `TenantAccountRepository` concreto é infraestrutura dependendo de infraestrutura. Nos testes basta um fake com `get_by_tenant`.
- **Não há cache, por três motivos:**
  1. **Custo irrelevante.** `fetch_entities` é chamado uma vez por run (a paginação reusa o mesmo adapter local) e `list_entity_types` uma vez por request. Uma consulta pela PK somada a um decrypt Fernet custa milissegundos. O custo real está no Orion (páginas de 1000) e no SLM (segundos por entidade).
  2. **Revogação imediata.** `update_broker`, `replace_tenant` e a remoção da conta passam a valer na próxima chamada. Com um TTL, uma chave comprometida e trocada continuaria em uso, ou um cliente removido continuaria sendo auditado.
  3. **Menos superfície de risco.** Um cache indexado por tenant é justamente o tipo de estrutura em que um erro de chave (por exemplo, indexar só por `fiware_service` e ignorar o `service_path`) vaza o broker de um tenant para outro. Sem cache, esse bug não pode existir.
- **Consistência dentro de um run:** a conta é lida uma vez por chamada de `fetch_entities`, e todas as páginas usam a mesma URL e a mesma chave.

## 3. Como enviar a `broker_api_key`: `Authorization: Bearer <chave>`

`OrionAdapter.__init__(self, base_url, client=None, *, api_key: str | None = None)`, além de um helper `_headers(tenant)` usado pelos dois métodos. O header só é adicionado quando `api_key is not None`. Sem chave, o dicionário de headers continua exatamente o de hoje.

Motivos para escolher `Authorization: Bearer` em vez de `X-Api-Key`, `apikey` ou `X-Auth-Token`:

- **Padrão:** é o esquema padronizado (RFC 6750), e Kong, Envoy, nginx e API Gateway validam esse header sem configuração especial.
- **Compatível com o caminho oficial do FIWARE:** o PEP Proxy Wilma aceita `Authorization: Bearer` (além de `X-Auth-Token`), e o Keyrock emite *permanent tokens*. A evolução para Keyrock, registrada como futura na ADR-0019, fica sem mudança de código: a "api key" passa a ser um token permanente do Keyrock.
- **Segurança por padrão:** `Authorization` é tratado como sensível pelas ferramentas. O httpx remove esse header em redirect cross-origin, enquanto headers customizados seriam repassados. Proxies e APMs costumam mascará-lo nos logs. Caches compartilhados não armazenam respostas autenticadas (RFC 9111 §3.5).
- **Enviado por requisição, nunca por cliente.** A chave vai em `headers=` de cada `get`. Nunca é colocada em `client.headers` nem em `client.auth`, porque o cliente é compartilhado.

Também acrescento `async def broker_url(self, tenant) -> str` ao `OrionAdapter`, que devolve a string recebida no construtor **sem** o `rstrip`. Assim, o valor gravado em `AuditRun.broker_url` no modo self-hosted continua idêntico ao de hoje, mesmo quando o `.env` tem barra final.

## 4. Riscos de segurança e mitigações

| Risco | Mitigação |
|---|---|
| **Cookie jar compartilhado.** Se o proxy do tenant A mandar um `Set-Cookie` (sessão), o httpx reenvia esse cookie ao mesmo host na chamada do tenant B. Isso importa quando dois tenants estão atrás do mesmo proxy (mesmo host, service paths diferentes), porque o proxy pode autenticar B como A. Confirmado empiricamente. | `get_broker_http_client()` exclusivo, com `DefaultCookiePolicy(allowed_domains=[])` (stdlib). |
| **Redirect repassando a chave para outro host.** | `follow_redirects=False` explícito no factory. O 3xx vira `ContextBrokerUnavailableError` via `raise_for_status`, que já trata qualquer resposta não-2xx. |
| **Chave definida no cliente em vez da requisição.** | A chave só vai em `headers=` por chamada. Um teste garante que `client.headers` continua sem `authorization` depois das chamadas. |
| **Reuso de conexão (keep-alive).** | Inofensivo para autenticação por header, que é por requisição. Proxies com autenticação orientada a conexão (NTLM/Kerberos) ficam fora do escopo; isso vai documentado. |
| **Vazamento da chave em logs.** O worker usa `logger.exception` e as mensagens incluem a URL. | A chave nunca entra em URL nem em mensagem. Teste: `str(err)` e `repr(err)` não contêm a chave (casos 401 e erro de rede). |
| **Credenciais na URL** (`https://user:pass@host`). O httpx envia Basic auth automaticamente e a URL completa vai para a mensagem de erro. | Ver ambiguidade 9.4. Não decido aqui. |
| **Segredo na fila.** Mensagens SQS e da DLQ são legíveis por quem tem `sqs:ReceiveMessage`. | O `AuditJob` **não** ganha `broker_url` nem `api_key`. O worker resolve pelo tenant. |
| **Job forjado na fila** (tenant arbitrário). | Está fora do código: é a IAM da fila (só a API pode fazer `SendMessage`). Registrar na ADR. |
| **SSRF pela `broker_url`.** | As contas são provisionadas pelo admin (sem self-signup), então o risco é baixo. Restrição de esquema e IP fica na ambiguidade 9.3. |
| **Proxies via `HTTP(S)_PROXY`** (`trust_env=True`). | Nota operacional. Não é alterado. |

## 5. JWT válido, mas a conta foi removida

**Nova exceção de domínio** em `domain/errors.py`:

```python
class TenantBrokerNotConfiguredError(DomainError):
    """Nao ha conta/broker cadastrado para este tenant (SaaS) — ex.: conta removida com JWT ainda valido."""
    def __init__(self, tenant: Tenant) -> None: ...
```

- Ela deriva de `DomainError` e **não** de `ContextBrokerUnavailableError`. Se derivasse, `GET /entity-types` a trataria como `broker_reachable=false` (200) e `process()` a trataria como falha transitória a ser reentregue. O problema é de identidade ou provisionamento, não de rede.
- Não há problema de import circular: `errors.py` passa a importar `Tenant`, que por sua vez importa `InvalidTenantError`. Para evitar o ciclo, uso `TYPE_CHECKING` ou tipo por string, ou guardo só `fiware_service`/`fiware_service_path` como strings. Escolho a última opção, a mais simples.

**Mapeamento HTTP:** um único handler em `create_app()`:

```python
app.add_exception_handler(TenantBrokerNotConfiguredError, _tenant_account_gone)
# -> 401 {"detail": "Conta nao encontrada; faca login novamente."}, WWW-Authenticate: Bearer
```

- O handler cobre `POST /audits`, via `start()` → `create_run()` → `broker_url()`, e `GET /entity-types`, cujo `except` só captura `ContextBrokerUnavailableError`.
- **Por que 401:** o token não corresponde mais a uma conta ativa, então a credencial deixou de valer. O frontend já trata 401 redirecionando para o login, e o login também vai falhar, o que é coerente. A resposta não confirma nem nega a existência de outro recurso e não expõe o nome do tenant.
- A alternativa (403 ou 409) está na ambiguidade 9.1.

**Worker:** ver a seção 6.

## 6. Impacto no `RunAuditUseCase` e no worker

**`broker_url` fixo no construtor não funciona mais no SaaS.** A instância é única para todos os tenants, e o `AuditRun.broker_url` gravado é a prova histórica do que foi auditado (ADR-0019 §6). No SaaS, gravar a URL global seria uma informação falsa.

**Decisão:** remover o kwarg `broker_url` do construtor e acrescentar ao port:

```python
async def broker_url(self, tenant: Tenant) -> str:
    """URL do broker que atende este tenant — gravada em AuditRun.broker_url.
    Levanta TenantBrokerNotConfiguredError se nao houver conta (SaaS)."""
```

Mudanças em `create_run()`:

```python
run = AuditRun.create(tenant=tenant, entity_type=entity_type,
                      broker_url=await self._context_broker.broker_url(tenant))
```

- **Falha antes de efeitos colaterais:** com a conta removida, `start()` falha antes de criar o run e antes de enfileirar. Não fica run órfão em `QUEUED`.
- **Por que não adotei um `broker_url: str | Callable` duplo, nem um resolver separado:** criaria dois caminhos para a mesma informação. Quem sabe qual broker atende um tenant é o próprio port de broker.
- **O que muda nos testes:** `_make_use_case` perde a linha 277, e `_FakeContextBroker` ganha `broker_url()`. Os fakes de REST (`_FakeContextBroker` e `_RecordingBroker`) não passam pelo use case e não mudam.

Mudanças em `process()` (worker):

```python
try:
    raw_entities = await self._context_broker.fetch_entities(tenant, entity_type, entity_id)
except TenantBrokerNotConfiguredError:
    async with self._uow as uow:
        await uow.audits.update_run_status(run_id, tenant, RunStatus.FAILED,
            finished_at=self._clock(), failure_reason="tenant_broker_not_configured")
    return
```

- O erro é **não reentregável**. Sem essa captura, o job seria reentregue N vezes, cairia na DLQ e seria marcado com `"max_retries_exceeded"`, um motivo enganoso. Com a captura, `process()` retorna normalmente, o `AuditWorker` faz `ack` e o Lambda não o inclui em `batchItemFailures`. Nenhuma mudança em `audit_worker.py` nem em `worker_handler.py`.
- `process_run()` (CLI) muda para `except (ContextBrokerUnavailableError, TenantBrokerNotConfiguredError)`, a mesma regra de run FAILED sem processamento.
- O caminho do worker **não usa JWT**. A identidade vem de `AuditJob.tenant`, que a API gravou a partir do tenant derivado do JWT em `get_tenant`. A cadeia de confiança é: JWT, depois `start()`, depois o job, depois `get_by_tenant(job.tenant)`.

## 7. Sequência TDD (vermelho → verde)

**Passo 0.** Rodar `pytest tests/unit` e anotar a contagem de testes como baseline.

**Passo 1. `OrionAdapter`** (`tests/unit/infrastructure/context_broker/test_orion_adapter.py`)
1. Regressão do self-hosted: sem `api_key`, a requisição **não** tem `authorization`, tanto em `fetch_entities` quanto em `list_entity_types`.
2. Com `api_key="k-a"`: `authorization == "Bearer k-a"` em `/v2/types` e em **todas** as páginas. Reusar o monkeypatch de `_PAGE_SIZE` do teste de paginação existente.
3. `client.headers` continua sem `authorization` após as chamadas com chave.
4. Em 401 do proxy e em `ConnectError`, a exceção `ContextBrokerUnavailableError` não contém `"k-a"` em `str()` nem em `repr()`.
5. Uma resposta 302 vira `ContextBrokerUnavailableError`, e o handler é chamado exatamente uma vez.
6. `await adapter.broker_url(t)` devolve a string do construtor literalmente, inclusive `"http://orion:1026/"` com barra final.
7. Implementar `api_key`, `_headers()` e `broker_url()`, e adicionar o método ao Protocol.

**Passo 2. `RunAuditUseCase`** (`tests/unit/application/test_run_audit_use_case.py`)
1. Ajustar `_make_use_case` (sem kwarg) e dar ao fake um `broker_url(tenant)` configurável por tenant. A suíte existente precisa continuar verde.
2. `create_run` para os tenants A e B grava a URL de A no run de A e a de B no run de B.
3. `start()` com `broker_url` levantando `TenantBrokerNotConfiguredError`: a exceção propaga, `repo.runs` fica vazio e `job_queue.enqueued` fica vazio.
4. `process()` com `fetch_entities` levantando o erro: não propaga, o run fica `FAILED` com `failure_reason == "tenant_broker_not_configured"` e `finished_at` preenchido.
5. `process_run()` no mesmo cenário: `FAILED`.
6. Implementar. Criar a exceção em `domain/errors.py`; `test_architecture.py` continua verde.

**Passo 3. `TenantRoutedContextBroker`** (novo `tests/unit/infrastructure/context_broker/test_tenant_routed_context_broker.py`). Usa um fake de repositório (`dict[Tenant, TenantAccount]`) e `httpx.MockTransport` que registra `(host, authorization, fiware-service, fiware-servicepath)`.
1. O tenant A vai para `orion-a.example.com` com `Bearer k-a` e os headers de A; o B, para B.
2. Conta com `broker_api_key=None`: sem `authorization`.
3. Conta inexistente: `TenantBrokerNotConfiguredError` com **zero** requisições HTTP, em `fetch_entities`, `list_entity_types` e `broker_url`.
4. **Sem cache:** trocar a URL e a chave no fake entre duas chamadas faz a segunda usar os novos valores; remover a conta faz a segunda levantar o erro.
5. **Mesmo `fiware_service`, service paths diferentes** (`("x","/a")` com `k-a` e `("x","/b")` com `k-b`), mesmo host: cada requisição leva a chave do seu path. Isso protege contra indexar só por `fiware_service`.
6. **Isolamento sob concorrência:** cerca de 20 tenants e cerca de 200 chamadas intercaladas via `asyncio.gather`, misturando `fetch_entities` (com paginação) e `list_entity_types`. O fake do repositório faz `await asyncio.sleep(random.random()/1000)` antes de responder, forçando intercalação. O handler também dorme. Asserção: toda tupla registrada é consistente (host, chave, service e path do **mesmo** tenant) e cada resultado devolvido pertence ao tenant que chamou. O handler devolve entidades com id prefixado pelo tenant.
7. **Caminho do worker, sem JWT:** um `RunAuditUseCase` real com o routed broker, fakes de UoW/catálogo/SLM (copiar os fakes mínimos) e dois `process()` concorrentes para A e B. Os reports do run de A só contêm entidades do broker de A. Os `run.broker_url` são corretos.
8. Implementar.

**Passo 4. Container** (novo `tests/unit/infrastructure/config/test_context_broker_factory.py`). O fixture `autouse` limpa `get_settings`, `get_engine`, `get_tenant_account_repository` e `get_broker_http_client`, no mesmo padrão de `test_tenant_account_repository_factory.py`.
1. Self-hosted (sem `DEPLOYMENT_MODE` e **sem** `BROKER_API_KEY_ENCRYPTION_KEYS`): `get_context_broker()` devolve um `OrionAdapter`, `_client is get_http_client()`, `_api_key is None`, e `broker_url` devolve `FIWARE_BROKER_URL` literal. Um monkeypatch em `get_tenant_account_repository` que levanta `AssertionError` nunca é disparado.
2. SaaS com as chaves: devolve `TenantRoutedContextBroker`, com `_client is get_broker_http_client()` e `is not get_http_client()`.
3. SaaS sem `BROKER_API_KEY_ENCRYPTION_KEYS`: `RuntimeError`.
4. `get_broker_http_client()`:
   - `follow_redirects is False`;
   - `client.cookies.extract_cookies(httpx.Response(200, headers={"set-cookie": "s=A; Path=/"}, request=httpx.Request("GET", "https://p.example.com/")))` resulta em `len(client.cookies) == 0`. Só API pública.
5. `get_run_audit_use_case()` constrói sem erro nos dois modos (smoke; `get_knowledge_retriever`/`get_embedder` são lazy, confirmar que não carregam o modelo).
6. Implementar.

**Passo 5. REST** (`tests/unit/interfaces/rest/test_auth.py`, no padrão `_client(monkeypatch, _SAAS, broker=...)` já existente)
1. `GET /entity-types` com o token A e depois com o token B, fazendo override de `get_context_broker` com um `TenantRoutedContextBroker(fake_repo, mock_client)` **real**: as requisições vão para o host e a chave de cada tenant. Um tenant **nunca** alcança o broker do outro, mesmo com o header `Fiware-Service` do outro forjado junto com o token (`_TENANT_HEADERS_B` já existe no arquivo).
2. Token válido e conta inexistente em `GET /entity-types`: 401, `WWW-Authenticate: Bearer`, e o body não contém o nome do tenant.
3. `POST /audits` com `get_run_audit_use_case` substituído por um fake cujo `start` levanta o erro: 401. Em `test_audits_router.py` ou `test_auth.py`.
4. Self-hosted: os testes existentes de `test_entity_types_router.py`/`test_audits_router.py` passam sem alteração.
5. Implementar o handler em `app.py`.

**Passo 6. Integração** (novo `tests/integration/context_broker/test_tenant_routed_context_broker_integration.py`, com `pytestmark = pytest.mark.integration` e o mesmo fixture de Postgres de `test_tenant_account_repository.py`). Repositório real, `MultiFernet` real e `MockTransport`.
1. Dois tenants criados via `create()`: roteamento e chave decifrada corretos.
2. Depois de `update_broker()`, a próxima chamada já usa a nova URL e a nova chave.
3. Depois de `DELETE` direto na tabela: `TenantBrokerNotConfiguredError`.
4. Depois de `rotate_encryption()` com a chave nova na frente: continua funcionando com a mesma chave em texto claro.

**Passo 7.** Rodar a suíte unitária completa e comparar com o baseline. Rodar a integração se houver Docker. Atualizar a documentação (seção 8).

## 8. Arquivos criados e alterados

**Criados**
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/context_broker/tenant_routed_context_broker.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/context_broker/test_tenant_routed_context_broker.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/config/test_context_broker_factory.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/context_broker/test_tenant_routed_context_broker_integration.py`

**Alterados**
- `src/auditor/domain/errors.py`: nova `TenantBrokerNotConfiguredError`.
- `src/auditor/domain/ports/context_broker_port.py`: novo `broker_url(tenant)`.
- `src/auditor/infrastructure/context_broker/orion_adapter.py`: `api_key` keyword-only, `_headers()` e `broker_url()`.
- `src/auditor/application/use_cases/run_audit.py`: remove o kwarg `broker_url`; `create_run` pergunta ao port; `process()` e `process_run()` tratam o novo erro.
- `src/auditor/infrastructure/config/container.py`: `get_broker_http_client()`, ramificação em `get_context_broker()` e remoção da linha 197.
- `src/auditor/interfaces/rest/app.py`: exception handler que responde 401.
- `tests/unit/infrastructure/context_broker/test_orion_adapter.py`, `tests/unit/application/test_run_audit_use_case.py`, `tests/unit/interfaces/rest/test_auth.py` (e eventualmente `test_audits_router.py`): novos testes.
- `docs/adr/adr-0019.md`: §1 marcado como implementado, com a convenção `Authorization: Bearer`, o requisito do proxy do produtor, a nota de IAM da fila e o motivo de não haver cache.
- `.env.example`: comentário de que `FIWARE_BROKER_URL` é ignorada em `DEPLOYMENT_MODE=saas`.

**Não mudam:** `audit_worker.py`, `worker/main.py`, `aws_lambda/worker_handler.py`, `worker_dlq_handler.py`, `AuditJob`, `sqs_job_queue.py`, `dependencies.py`, `tenant_account_repository.py` e as migrations.

## 9. Ambiguidades para o usuário decidir

1. **Status HTTP para "JWT válido, conta removida":** proponho 401 com reautenticação. As alternativas são 403, que sinaliza "identidade ok, sem permissão", e 409 ou 422, que sinalizam "conta sem broker". Isso afeta o frontend.
2. **Revogação nos endpoints de leitura:** `GET /audits*` não toca no broker. Um token de conta removida continua lendo o histórico até expirar (padrão de 60 min). Opções: aceitar, ou fazer `get_tenant` consultar `tenant_accounts` em toda requisição SaaS (uma consulta a mais por request).
3. **Exigir `https://` e bloquear IPs privados ou de metadata** (169.254.169.254) na `broker_url` em SaaS, no `audit tenant register` e no `update_broker`. Hoje as URLs são provisionadas pelo admin; a ADR fala de um proxy HTTPS como requisito do produtor, mas nada obriga isso.
4. **Proibir userinfo** (`user:pass@`) na `broker_url`: a URL vazaria em logs e mensagens de erro, e seria enviada como Basic auth sem aviso.
5. **Header configurável por tenant:** `Authorization: Bearer` é fixo neste plano. Se algum produtor usar um proxy que espera `X-Api-Key` ou `apikey`, seria preciso uma coluna nova e uma migration.
6. **Troca de broker entre o enfileiramento e o processamento:** o `AuditRun.broker_url` grava a URL no momento do `start()`, mas o worker resolve de novo. Se o admin trocar o broker nesse intervalo, o run registra a URL antiga e audita a nova. Opções: aceitar, fazer o worker comparar com `run.broker_url` e falhar, ou fazer o worker sobrescrever o valor.
7. **Self-hosted com a futura tela de Configuração** (ADR-0019 §2, que grava em `tenant_accounts`): quando ela existir, o self-hosted deve passar a rotear por `tenant_accounts` também? Hoje o requisito é manter o self-hosted byte-idêntico, lendo o `.env`.
8. **`ORION_CREDENTIALS_JSON`/Parameter Store** (`_bootstrap.py`, `secrets_bootstrap.py`, Terraform) continua sem consumidor. Com as credenciais por tenant no Postgres, deve ser removido ou mantido para algum outro fim?
9. **CLI `audit run` em modo SaaS:** passaria a auditar o broker do tenant indicado em `--tenant`, sem autenticação (é uma ferramenta de admin com acesso ao banco). Isso é desejado, ou a CLI deveria recusar `run` em SaaS?
10. **`failure_reason` exibido ao usuário:** o texto `"tenant_broker_not_configured"` aparece na API (`AuditRunResponse`). Confirmar o nome e se o frontend precisa de uma tradução.

### Arquivos críticos para a implementação
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/container.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/context_broker/orion_adapter.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/application/use_cases/run_audit.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/domain/ports/context_broker_port.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py
