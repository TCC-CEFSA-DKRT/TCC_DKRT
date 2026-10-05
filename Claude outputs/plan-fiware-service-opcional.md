# Plano: `Fiware-Service` vazio em modo self-hosted (Orion sem multi-tenancy)

## 0. Resumo

O que realmente bloqueia não é o banco. É o **value object `Tenant`**, que levanta `InvalidTenantError` para `""`. Todo caminho (router, mapper do banco, fila SQS, CLI, JWT) passa pelo construtor dele. Relaxar isso, mais quatro ajustes pontuais, resolve a cadeia inteira:

1. `OrionAdapter` omite o header quando o service é vazio.
2. `get_tenant()` no self-hosted passa a derivar o tenant da conta salva (opção b).
3. O regex do schema aceita vazio.
4. Os guards de SaaS ficam no JWT e na CLI.

Nenhuma migration é necessária.

---

## 1. `Tenant` value object

`src/auditor/domain/value_objects/tenant.py`: **sim, rejeita vazio hoje**.

```python
def __post_init__(self) -> None:
    if not self.fiware_service:
        raise InvalidTenantError("Tenant.fiware_service e obrigatorio e nao pode ser vazio.")
```

**Mudança:** apagar o `__post_init__` e ajustar a docstring. O `fiware_service == ""` passa a significar "serviço default do Orion (sem multi-tenancy)", que é a semântica do próprio NGSI-v2. Com isso o domínio modela o Orion e não precisa saber o modo de deployment. A exigência de "não vazio em SaaS" é regra de aplicação e vai para as fronteiras SaaS (item 3b).

Efeito colateral: `InvalidTenantError` deixa de ser levantado em qualquer lugar. Só existe em `domain/errors.py:12` e nos `except` de `interfaces/rest/dependencies.py:50` e `interfaces/rest/routers/session.py:35`. Recomendo apagar os três (código morto). O teste `tests/unit/domain/test_value_objects.py::TestTenant::test_empty_fiware_service_raises` inverte.

## 2. `OrionAdapter`

`src/auditor/infrastructure/context_broker/orion_adapter.py:34-41`. Hoje manda sempre os dois headers, inclusive `Fiware-Service: ""`. Um header vazio e um header ausente não são garantidamente equivalentes no Orion nem em proxies, então a chave deve ser omitida:

```python
def _headers(self, tenant: Tenant) -> dict[str, str]:
    headers = {"Fiware-ServicePath": tenant.fiware_service_path}
    if tenant.fiware_service:
        headers["Fiware-Service"] = tenant.fiware_service
    if self._api_key is not None:
        headers["Authorization"] = f"Bearer {self._api_key}"
    return headers
```

O `Fiware-ServicePath` continua sempre sendo enviado, porque `/` é válido e o Orion aceita service path no tenant default. Como `fetch_entities` e `list_entity_types` usam `_headers()`, a correção fica num lugar só.

`TenantRoutedContextBroker` (SaaS) e `SelfHostedContextBroker` **não mudam**. Um ponto da rodada anterior precisa de correção: `SelfHostedContextBroker._adapter_for` ignora o tenant **só para escolher a URL**. Em seguida, `adapter.fetch_entities(tenant, ...)` recebe o tenant **da requisição**. Hoje, portanto, o `Fiware-Service` enviado ao Orion vem do header HTTP e não da conta salva. As duas fontes só coincidem porque o frontend copia `session.tenant` para o header. Esse é o principal argumento para a opção (b).

## 3. `get_tenant()` no self-hosted: recomendo **(b)**

### Onde `Tenant` importa depois de `get_tenant()`

- `routers/audits.py` (7 rotas) e `routers/entity_types.py`.
- Vai para o use case, depois para o `context_broker.fetch_entities(tenant)` e daí para os **headers enviados ao Orion** (item 2).
- Também vai para `postgres_audit_repository.py` (linhas 62, 155, 168, 183, 204, 240, 278): **o escopo de `audit_runs`** (listagem, get e progress filtram por `tenant_fiware_service`/`path`).
- E para `sqs_job_queue.py:36`, onde é serializado no job e consumido depois pelo worker.

Ou seja, o valor importa em dois lugares: o que vai para o Orion e quais runs o usuário enxerga.

### Por que não (a)

Para (a) funcionar, o navegador teria que mandar `Fiware-Service: ` com valor vazio. O Angular até manda, mas usar "header presente e vazio" como sinal é frágil atrás de nginx/proxy. Na prática, (a) acaba aceitando "header ausente", o que elimina o 401 de qualquer jeito. Aí um curl sem header audita o tenant default enquanto a UI está configurada com "openiot": duas fontes da verdade, e runs aparecendo em listas diferentes.

### (b): uma fonte só, a conta salva, igual a `/session`, `/config` e `SelfHostedContextBroker`

```python
async def get_tenant(
    token: str | None = Depends(session_token),
    settings: Settings = Depends(get_settings),
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
) -> Tenant:
    if settings.deployment_mode == "saas":
        if token is None:
            raise _unauthorized("Sessao ausente: faca login.")
        try:
            return tenant_from_access_token(token, settings)
        except jwt.InvalidTokenError:
            raise _unauthorized("Token invalido ou expirado.") from None

    account = await accounts.get_single() if accounts is not None else None
    if account is not None:
        return account.tenant
    # sem chave Fernet, ou chave sem conta salva: mesmo fallback de URL do SelfHostedContextBroker
    return Tenant(settings.fiware_service, settings.fiware_service_path)
```

Os parâmetros `Header(...)` saem. Atualizar a docstring do módulo e o comentário de CORS em `app.py:107` (`allow_headers=["*"]` continua).

**Ramo sem chave Fernet:** hoje ainda depende do header. Com (b), usa `Settings.fiware_service/path`, exatamente o que `/session` já devolve nesse ramo e o que o frontend reenvia como header. Para a UI, o comportamento é idêntico. `FIWARE_SERVICE=` vazio no `.env` vira `""`, porque o pydantic-settings não ignora env vazio por padrão.

### (b) quebra, e é esperado

| Teste | Hoje | Depois |
|---|---|---|
| `tests/unit/interfaces/rest/test_audits_router.py::TestCreateAudit::test_missing_tenant_header_returns_401` | 401 | reescrever: sem header retorna 202 com o tenant de Settings |
| `tests/unit/interfaces/rest/test_entity_types_router.py::test_missing_tenant_header_returns_401` | 401 | idem |
| `tests/unit/interfaces/rest/test_auth.py::test_b12_bearer_header_is_ignored_tenant_comes_from_headers` | recebe `tenant_b` | o broker recebe `Tenant("openiot","/")` (Settings), e `tenant_b` do header é ignorado |
| `tests/unit/interfaces/rest/test_auth.py::test_missing_tenant_header_still_returns_401` | 401 | reescrever: 200 |
| `tests/integration/test_run_audit_e2e.py` | header `auditor_fase4_e2e` | somar `monkeypatch.setenv("FIWARE_SERVICE", "auditor_fase4_e2e")` no fixture `wired_app` |

Além disso, a fixture `app_and_repo` do `test_audits_router.py` não sobrescreve `get_settings` e passaria a depender de `get_selfhosted_accounts`, ou seja, do `.env` real. Se o `.env` de alguém tiver `BROKER_API_KEY_ENCRYPTION_KEYS`, esses testes tentariam acessar o Postgres. Somar `app.dependency_overrides[get_selfhosted_accounts] = lambda: None` e `get_settings = lambda: Settings(_env_file=None)`. Fazer o mesmo na fixture de `test_entity_types_router.py`.

**`src/auditor/experiment/run_experiment.py`** (o harness do experimento do TCC) é afetado. Ele carrega entidades no Orion com `Fiware-Service: experiment` e chama a API do Auditor com o mesmo header para isolar o experimento dos dados reais. Com (b), a API ignora esse header, e o operador precisa subir a API com `FIWARE_SERVICE=experiment` (sem Fernet) ou salvar `experiment` em `/config`. Ver ambiguidade A2 — decidido: (ii).

### 3b. Guards de SaaS (o value object não os faz mais)

- `src/auditor/interfaces/rest/access_tokens.py:42`. É a função compartilhada por `get_tenant` (SaaS) e `/session` (SaaS):
  ```python
  if not isinstance(service, str) or not isinstance(path, str) or not service:
      raise jwt.InvalidTokenError("claims de tenant com tipo invalido")
  ```
  Isso mantém `test_b9_empty_fiware_service_is_401` passando sem alteração.
- A CLI `tenant register --email` fica no item 6. Essa é a única forma de criar uma conta SaaS: `PUT /config` retorna 404 em SaaS, como já coberto por `test_put_config_is_404_in_saas`.

## 4. Schemas

`src/auditor/interfaces/rest/schemas.py:45`:

```python
fiware_service: str = Field(pattern=r"^[A-Za-z0-9_]{0,50}$")
```

O campo continua obrigatório no corpo; o frontend sempre o envia. `fiware_service_path` fica como está: o regex `^/(...)?$` já exige `/`. `BrokerConfigResponse` e `TenantResponse` não têm pattern e não mudam. `test_crlf_in_fiware_service_is_422` continua válido.

`routers/config.py` não muda: `replace_tenant("openiot" -> "")` já faz delete+insert e a PK `("", "/")` é válida.

## 5. `tenant_accounts`: sem migration

- `tables.py:158-170` e a migration `edfd0898f739_add_tenant_accounts_table.py` só têm `NOT NULL`, a PK composta, `uq_tenant_accounts_login_email`, `ck_tenant_accounts_login_pair` e `ck_tenant_accounts_broker_url_not_empty`. **Não há CHECK nem índice sobre `fiware_service <> ''`.**
- `audit_runs.tenant_fiware_service` também é só `NOT NULL`. O índice `(tenant_fiware_service, tenant_fiware_service_path, started_at)` funciona com `""`.
- Não há lógica do tipo `if fiware_service:` na persistência. Só aparecem mensagens cosméticas (`f"{service}/{path}"` vira `"//"`), em `tenant_account_repository.py:165,192,197`. Não vale mexer.

## 6. CLI

`src/auditor/interfaces/cli/main.py`.

- **`tenant register`**: `--tenant` é `typer.Option(...)` obrigatório, e `--tenant ""` já passa `""` ao Typer. Depois do item 1, ele funciona sozinho. Não precisa de flag nova. Falta só o guard de SaaS, no mesmo estilo do guard de `--password` existente:
  ```python
  if email is not None and not tenant:
      typer.echo("--email (conta SaaS) exige --tenant nao vazio.", err=True)
      raise typer.Exit(code=1)
  ```
- **`run`/`status`** (`_resolve_tenant`, linha 51): `tenant or settings.fiware_service` transforma `--tenant ""` no valor de Settings. Trocar para `tenant if tenant is not None else settings.fiware_service`. O `service_path` pode continuar com `or`, porque path vazio não é válido.

## 7. Frontend

- `frontend/src/app/features/config/config.component.html:27-35`: tirar o `required` do input `fiwareService`. Não existe `pattern` no template. Como o `FormsModule` adiciona `novalidate`, o `required` nunca bloqueou nada de fato: o erro vinha do 422. Adicionar uma dica abaixo do input:
  ```html
  <small class="config-field__hint">Deixe em branco se o broker não usa isolamento por serviço (Fiware-Service) do Orion.</small>
  ```
  O `.scss` não tem classe de hint para campos: somar `.config-field__hint { font-weight: 400; color: var(--color-text-secondary); font-size: 0.8125rem; }`.
- `config.component.ts`: nada muda. `this.fiwareService.trim()` já envia `""`, e `session.set({tenant: {fiware_service: ''}})` produz um objeto truthy, então `app.guard.ts` continua deixando passar.
- `frontend/src/app/core/tenant.interceptor.ts:20-27`: com (b), o bloco `setHeaders` do self-hosted deixa de ter efeito. **Apagar** o bloco, o que também evita o `Fiware-Service: ` vazio saindo do navegador. O `withCredentials` e o tratamento de 401 continuam.

## 8. Dados existentes

Nenhuma linha pode ter `""`. O value object rejeitava vazio em toda construção, inclusive em `create()`/`replace_tenant()` e na leitura (`_to_account`, `mappers.py`), então uma linha vazia só existiria por SQL manual e, se existisse, quebraria hoje na leitura. Não há migração de dados.

---

## Sequência TDD

**Backend**

1. `tests/unit/domain/test_value_objects.py`: substituir `test_empty_fiware_service_raises` por `test_empty_fiware_service_is_the_orion_default_service` (`Tenant("")` constrói, com path `/`).
2. `tests/unit/infrastructure/context_broker/test_orion_adapter.py`:
   - `test_empty_service_omits_fiware_service_header`: com `MockTransport`, capturar `request.headers` e verificar `"fiware-service" not in headers` e `headers["fiware-servicepath"] == "/"`, tanto em `fetch_entities` quanto em `list_entity_types`.
   - `test_non_empty_service_sends_header` (regressão).
3. `tests/unit/interfaces/rest/test_auth.py`: `test_b9_empty_fiware_service_is_401` precisa continuar verde depois do passo 1. Rodar antes do guard do `access_tokens` para ver ficar vermelho.
4. Testes de `get_tenant` self-hosted, em `test_entity_types_router.py` (ou em `test_auth.py::TestGetTenantSelfHostedRegression`), com `_RecordingBroker`:
   - chave Fernet e conta salva com `Tenant("", "/")`: o broker recebe `Tenant("", "/")`, mesmo com header `Fiware-Service: tenant_b`;
   - chave Fernet sem conta: recebe o tenant de Settings;
   - sem chave e `Settings(fiware_service="")`: recebe `Tenant("")`;
   - sem nenhum header: 200, não 401.

   Reescrever os 4 testes da tabela do item 3 e ajustar as fixtures (overrides de `get_selfhosted_accounts` e `get_settings`).
5. `tests/unit/interfaces/rest/test_config_router.py`:
   - `test_put_empty_fiware_service_is_accepted`: 200, `create` chamado com `Tenant("", "/")`;
   - `test_get_config_returns_empty_service` (conta salva com `""`);
   - `test_fiware_service_over_50_chars_is_422`.
6. `tests/unit/interfaces/rest/test_session_router.py`: conta salva com `""` faz `tenant.fiware_service == ""`.
7. `tests/unit/infrastructure/queue/test_sqs_job_queue.py`: round-trip de um job com `Tenant("")`. É barato e cobre o worker.
8. `tests/integration/test_run_audit_e2e.py`: somar o `setenv FIWARE_SERVICE`. Opcional, marcado `integration`: em `tests/integration/context_broker/test_orion_adapter_integration.py`, criar uma entidade no Orion real **sem** `Fiware-Service` e verificar que `OrionAdapter.fetch_entities(Tenant(""))` a encontra. É o único teste que prova o comportamento real do Orion.

**CLI**, em `tests/unit/interfaces/cli/test_cli.py`, classe `TestTenantRegisterCommand`:

9. `test_c8_empty_tenant_without_email_creates_self_hosted_row`: `create_calls[0]` recebe `Tenant("", "/")`.
10. `test_c9_empty_tenant_with_email_is_rejected_without_calling_create`: exit != 0, `create_calls == []`.
11. `test_run_with_explicit_empty_tenant_overrides_settings` (`--tenant ""` com Settings `openiot`: o use case recebe `Tenant("")`).

**Frontend**

12. `frontend/src/app/core/tenant.interceptor.spec.ts`: trocar "attaches Fiware-Service/... in self-hosted mode" por "never attaches tenant headers in self-hosted mode" (`headers.has('Fiware-Service') === false`).
13. `frontend/src/app/features/config/config.component.spec.ts`: `sends an empty fiware_service when the field is left blank` (o corpo do PUT tem `fiware_service: ''`, e depois do flush `session.session()?.tenant?.fiware_service === ''`). Opcional: consultar o DOM para confirmar que o input não tem o atributo `required` e que a dica está renderizada.

---

## Arquivos afetados

| Arquivo | Mudança |
|---|---|
| `src/auditor/domain/value_objects/tenant.py` | remove `__post_init__` e ajusta a docstring |
| `src/auditor/domain/errors.py` | remove `InvalidTenantError` (código morto) |
| `src/auditor/infrastructure/context_broker/orion_adapter.py` | `_headers()` omite `Fiware-Service` vazio |
| `src/auditor/interfaces/rest/dependencies.py` | `get_tenant()` self-hosted usa `get_single()` ou Settings; remove os params `Header` |
| `src/auditor/interfaces/rest/access_tokens.py` | rejeita `fiware_service` vazio no JWT |
| `src/auditor/interfaces/rest/routers/session.py` | remove `InvalidTenantError` do except |
| `src/auditor/interfaces/rest/schemas.py` | `{1,50}` passa a `{0,50}` |
| `src/auditor/interfaces/rest/app.py` | comentário de CORS |
| `src/auditor/interfaces/cli/main.py` | guard `--email` com tenant vazio; `_resolve_tenant` usa `is None` |
| `src/auditor/experiment/run_experiment.py` | checagem barata via `GET /session` (decisão A2) |
| `selfhosted/docker-compose.yml` / `docker-compose.selfhosted.yml` | `FIWARE_SERVICE: ""` no prefill (decisão A3) |
| `frontend/src/app/features/config/config.component.html` / `.scss` | remove `required`, adiciona dica |
| `frontend/src/app/core/tenant.interceptor.ts` | remove o bloco de headers self-hosted |
| testes listados acima | ~8 arquivos |
| `tables.py` / migrations | **nenhuma mudança** |

---

## Decisões (já tomadas, não é mais ambiguidade)

- **A1** (conta ausente com chave Fernet configurada): fallback para o tenant de Settings em `get_tenant()`, coerente com `SelfHostedContextBroker`.
- **A2** (`run_experiment.py`): opção (ii) — soma um check barato de `GET /session` no harness, abortando se o tenant não bater.
- **A3** (prefill padrão do `.env`/compose): troca `FIWARE_SERVICE: openiot` para `FIWARE_SERVICE: ""` nos dois composes self-hosted, porque o caso mais comum é sem multi-tenancy.
- **A4** (CHECK no banco): pular, sem migration.
- **A5** (CLI `run`/`status`): deixa como está, ferramenta de admin/dev.
- **A6** (job em fila durante troca de `/config`): não tratar agora, edge case pré-existente.

### Critical Files for Implementation
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/domain/value_objects/tenant.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/context_broker/orion_adapter.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/rest/dependencies.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/rest/access_tokens.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/rest/schemas.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/cli/main.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/frontend/src/app/features/config/config.component.html
- /mnt/user-data/uploads/agent_multi_IA_context_broker/frontend/src/app/core/tenant.interceptor.ts
