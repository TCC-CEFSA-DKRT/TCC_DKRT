# Plano: Login (SaaS, cookie httpOnly) + gate de Configuração (self-hosted)

Plano só de leitura. Tudo abaixo foi conferido no código em `/mnt/user-data/uploads/agent_multi_IA_context_broker`. Onde o código contradiz o briefing, isso aparece como **Correção**.

---

## 0. Onde o código contradiz o briefing (ler antes de tudo)

1. **O self-hosted não usa `tenant_accounts` hoje em lugar nenhum.** No modo self-hosted o broker vem de `Settings.fiware_broker_url` (`container.py:125`, `OrionAdapter(settings.fiware_broker_url, ...)`) e o tenant vem dos headers (`dependencies.py:47-55`). Para o gate ter efeito real, o *runtime* do self-hosted precisa passar a ler a linha salva. Esse é o trabalho escondido do plano: dois endpoints REST sozinhos não resolvem.
2. **A ADR-0019 também diverge do código.** A linha 62 diz que no self-hosted "o tenant continua vindo de `Settings.fiware_service`", mas o código lê o header `Fiware-Service`. A linha 108 cita a flag `environment.selfHosted`, que não existe: não há `frontend/src/environments/` nem `fileReplacements` no `angular.json`.
3. **O repositório é assíncrono.** O briefing diz que `create`/`update_broker`/`replace_tenant` são "síncronos", mas os três são `async def` (`tenant_account_repository.py:61,129,156`).
4. **`Domain=<raiz>` não é necessário e piora a segurança.** O cookie só precisa voltar para a própria API que o definiu. Um cookie *host-only* em `api.X` já é enviado nos XHR com credenciais vindos de `app.X`, porque os dois são *same-site* (mesmo eTLD+1, `exemplo.com`). Com `Domain=` na raiz, o JWT iria para todos os subdomínios. A decisão é: sem `Domain`.
5. **Tabela `tenant_accounts` tem uma coluna a mais.** Ela também tem `broker_api_key_encrypted` (`tables.py:161`), não só os três campos do briefing. A recomendação sobre ela está na seção 2.3.
6. **Achado de segurança no CORS.** O Starlette 1.0.0 instalado *reflete qualquer Origin* quando `allow_origins=["*"]` e `allow_credentials=True` (`starlette/middleware/cors.py`, linhas 166-168 do fonte: `if self.allow_all_origins and self.allow_credentials: self.allow_explicit_origin(...)`). Hoje nada define `"*"` (produção usa `module.frontend_delivery.frontend_url`, `production/main.tf:156`), mas com autenticação por cookie isso passa a ser um risco de configuração que precisa de guarda.
7. **Bug no bundle self-hosted, independente deste trabalho.** O serviço `app` em `selfhosted/docker-compose.yml` não define `CORS_ALLOWED_ORIGINS`, então vale o default `http://localhost:4200`, mas o frontend do bundle roda em `:5173` (linha 147). A UI do bundle já é bloqueada por CORS hoje, e o gate não funciona sem corrigir isso.

Confirmado como o briefing dizia: o router `auth` só é montado em `saas` (`app.py:113-114`), então o **cookie de sessão é assunto só do SaaS**. O self-hosted não tem login nem JWT.

---

## 1. Backend: cookie de sessão (SaaS)

### 1.1 `POST /auth/login` passa a enviar `Set-Cookie`

Os atributos, cada um com o motivo:

| Atributo | Valor | Motivo |
|---|---|---|
| nome | `auditor_session` (constante `SESSION_COOKIE_NAME` em `access_tokens.py`) | Usado por `auth.py` e `dependencies.py`, num lugar só |
| `HttpOnly` | sempre | É o motivo de usar cookie |
| `Secure` | sempre (fixo no código) | Chrome trata `http://localhost` como contexto seguro para cookies `Secure`, então o dev SaaS em `localhost:4200 → localhost:8000` funciona. Um flag desligável em produção seria uma armadilha. **Validar no navegador do dev**; se falhar (Safari, IP da LAN), aí sim criar `SESSION_COOKIE_SECURE: bool = True` |
| `SameSite` | `Strict` | Ninguém navega direto para a API. XHR de `app.X` para `api.X` é same-site e continua recebendo o cookie. Isso bloqueia CSRF vindo de outros sites |
| `Domain` | omitido (host-only) | Ver Correção 4 |
| `Path` | `/` | |
| `Max-Age` | `settings.jwt_expiration_minutes * 60` | Mesma origem do `exp` emitido em `issue_access_token` |

Esboço, preservando o padrão anti-timing (`_dummy_password_hash` + `asyncio.to_thread`) sem tocar nele:

```python
@router.post("/login", response_model=AccessTokenResponse)
async def login(body: LoginRequest, response: Response, settings=..., repository=...) -> AccessTokenResponse:
    ...  # verificação inalterada
    token = issue_access_token(account.tenant, settings)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, max_age=settings.jwt_expiration_minutes * 60,
        path="/", secure=True, httponly=True, samesite="strict",
    )
    return AccessTokenResponse(access_token=token)
```

**O corpo continua com o JWT.** Clientes não-navegador (curl, scripts) continuam usando `Authorization: Bearer`, e `test_b11_real_round_trip_login_then_entity_types` segue passando. O frontend ignora o corpo. O custo é pequeno: um XSS na página de login conseguiria ler o token, mas um XSS já age com o cookie dentro da página de qualquer jeito. Tirar o token do corpo fica listado nas ambiguidades.

### 1.2 `get_tenant` aceita o cookie

Uma dependência pequena extrai o token, e `get_tenant` passa a usá-la. **O Bearer tem precedência sobre o cookie.** O caminho self-hosted não muda.

```python
def session_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str | None:
    return credentials.credentials if credentials else cookie
```

Dentro de `get_tenant`, no modo saas: `if token is None: raise _unauthorized("Sessao ausente: faca login.")`. O resto continua igual.

### 1.3 `POST /auth/logout`: precisa existir

Com cookie `HttpOnly`, o JavaScript não consegue apagar o cookie, então sem esse endpoint não existe logout. Ele responde 204 com `response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")` (os mesmos atributos, para o navegador aceitar a remoção). Não exige autenticação e é idempotente.

O JWT não é revogado no servidor (é stateless). Um token vazado vale até o `exp`, no máximo 60 min. Isso é aceitável e deve ser documentado.

### 1.4 `GET /session`: um endpoint público, nos dois modos

Esse endpoint responde de uma vez três perguntas do frontend: qual o `deployment_mode`, se pode entrar e qual o tenant.

```python
class SessionResponse(BaseModel):
    deployment_mode: Literal["saas", "selfhosted"]
    tenant: TenantResponse | None   # {fiware_service, fiware_service_path}
```

- **saas:** decodifica o token vindo de `session_token`. Se não houver token ou ele for inválido, devolve `tenant=None` com **200, nunca 401**. É uma sonda sem ruído no console.
- **selfhosted:** devolve o tenant da linha salva, ou `None` se não houver configuração (seção 2).

Isso **substitui a flag de build `environment.selfHosted` da ADR** (que nunca foi criada). A mesma build do frontend serve os dois modos, sem risco de build e backend discordarem, e não precisa de `fileReplacements`. Também dispensa um `/auth/me` separado. Arquivo novo: `routers/session.py`, montado sempre.

### 1.5 Settings

- **Nenhum campo novo de cookie.** `Domain` é omitido e `Secure` é sempre ligado.
- **Um validator novo** que rejeita `"*"` em `cors_allowed_origins_list` quando `deployment_mode == "saas"` (Correção 6). Uma linha, ao lado de `_require_jwt_signing_key_in_saas`.

---

## 2. Backend: gate de Configuração (self-hosted)

### 2.1 Fazer o runtime do self-hosted usar a linha salva

**`TenantAccountRepository.get_single()`** (novo). Devolve a única conta sem login, ou `None`:

```python
async def get_single(self) -> TenantAccount | None:
    """Self-hosted (ADR-0019 sec. 2): a unica conta da instalacao."""
    ... select(t).where(t.c.login_email.is_(None)).limit(2) ...
    if len(rows) > 1:
        raise LookupError("mais de uma conta self-hosted em tenant_accounts")  # ex.: `tenant register` rodado 2x
    return self._to_account(rows[0]) if rows else None
```

**`SelfHostedContextBroker(TenantRoutedContextBroker)`** (novo, cerca de 12 linhas). Sobrescreve só `_adapter_for`. Usa um broker por instalação e **ignora o tenant na busca**:

```python
async def _adapter_for(self, tenant: Tenant) -> OrionAdapter:
    account = await self._accounts.get_single()
    if account is None:
        return OrionAdapter(self._default_broker_url, client=self._client)
    return OrionAdapter(account.broker_url, client=self._client, api_key=account.broker_api_key)
```

Por que não reaproveitar direto o `TenantRoutedContextBroker` (que busca por tenant)? Porque `run_experiment.py` (`src/auditor/experiment/run_experiment.py:162-165`), o e2e (`test_run_audit_e2e.py:33`) e `audit run --tenant X` usam tenants arbitrários no *mesmo* Orion. Com busca por tenant, todos passariam a dar `TenantBrokerNotConfiguredError`. O fallback para `FIWARE_BROKER_URL` quando não há linha mantém esses três funcionando sem nenhum passo novo.

**`container.get_context_broker()`**:

```python
if settings.deployment_mode == "saas":
    return TenantRoutedContextBroker(...)                      # inalterado
if not settings.broker_api_key_encryption_keys_list:
    # ponytail: sem chave Fernet nao existe configuracao salva possivel (dev sem .env,
    # homolog/academy EC2) -- so' o .env, comportamento pre-gate. Bundle gera a chave sozinho.
    return OrionAdapter(settings.fiware_broker_url, client=get_http_client())
return SelfHostedContextBroker(get_tenant_account_repository(), client=get_http_client(),
                               default_broker_url=settings.fiware_broker_url)
```

Esse ramo "sem chave" preserva a invariante da ADR-0019 §7 e o teste `test_returns_an_orion_adapter_over_the_shared_http_client_without_api_key` (que apaga a variável de chave). Também mantém o smoke `test_builds_without_error_in_selfhosted`, o `.env` local (que não tem a chave) e o homolog/academy (cujo `user_data` também não tem). Sem ele, o lifespan (`app.py`, `get_run_audit_use_case()` no startup) quebraria com `RuntimeError` nesses ambientes.

Para `/session` e `/config` reaproveitarem a mesma regra, cria-se um helper no container:

```python
def get_selfhosted_accounts() -> TenantAccountRepository | None:
    return get_tenant_account_repository() if get_settings().broker_api_key_encryption_keys_list else None
```

### 2.2 Endpoints: `routers/config.py`, montado só em `selfhosted` (espelho do `auth`)

| Método | Resposta |
|---|---|
| `GET /config` | `{configured, broker_url, fiware_service, fiware_service_path}`. É a linha salva, ou os valores de `Settings` como **pré-preenchimento** quando `configured=false`. No bundle, isso faz `http://orion:1026` já vir preenchido e o usuário só confirma. **Nunca devolve a api key.** Sem chave Fernet: `configured=true` com os valores do `.env`, igual ao `/session` |
| `PUT /config` | Se não há linha, chama `create(tenant, broker_url)`. Se há, chama `replace_tenant(old=atual.tenant, new, broker_url, broker_api_key=None)` (DELETE+INSERT atômico, exatamente como a ADR §2 previa). Devolve o mesmo formato do GET. Sem chave Fernet: 503 com mensagem explícita |

`/session` no self-hosted segue a mesma regra: sem chave, o tenant vem de `Settings.fiware_service/_path`; com chave, vem de `get_single()`, ou `None`, o que aciona o gate.

`get_tenant` no self-hosted **não muda** (continua lendo os headers). Quem envia o tenant é o frontend, lendo `/session`. Com isso nenhum teste existente de router self-hosted quebra.

**Autenticação:** nenhuma. Não é um buraco novo: o self-hosted já é inteiramente não autenticado (`POST /audits` aceita qualquer tenant via header). O limite de confiança é a rede do produtor, e montar o router só em self-hosted impede estruturalmente um PUT anônimo no SaaS. Risco residual: SSRF, porque quem alcança `:8000` pode apontar o broker para qualquer URL. Isso fica documentado. Publicar `127.0.0.1:8000:8000` no compose fica nas ambiguidades.

### 2.3 Campos do payload

A inclinação do briefing se confirma: `broker_url`, `fiware_service`, `fiware_service_path` (default `/`). Todos são validados no limite de confiança, porque viram **headers HTTP enviados ao Orion** e, sem validação, abririam espaço para injeção de CRLF:

- `broker_url`: `pattern=r"^https?://\S+$"`. O self-hosted aceita `http://` porque `require_https=False` fora do saas (`container.py:87`).
- `fiware_service`: `pattern=r"^[A-Za-z0-9_]{1,50}$"` (regra do Orion).
- `fiware_service_path`: `pattern=r"^/([A-Za-z0-9_]+(/[A-Za-z0-9_]+)*)?$"`.

Sobre as outras colunas da tabela:
- **Nome do tenant:** não existe, porque o tenant *é* o `fiware_service`.
- **`broker_api_key`:** fica **fora** do formulário. A ADR §2 diz que o self-hosted é "sem api_key", e o Orion do bundle não tem PEP. Consequência documentada: salvar pela UI grava `None` e apaga uma chave eventualmente cadastrada via `tenant register --broker-api-key`. Preservar a chave antiga seria pior: se a `broker_url` mudar, a chave vazaria para outro host. Adicionar o campo depois custa um input write-only mais um repasse.
- **"Tipos de entidade":** não viram campo. A ADR (linha 110) e a docstring de `routers/entity_types.py:1-6` citam tipos de entidade na tela de configuração, mas se referem à **descoberta** (`GET /entity-types`, que já existe e hoje nenhuma tela do frontend usa), não a um valor salvo. Não há nada em `Settings`, na CLI ou no schema que guarde tipos. Proposta: usar o endpoint depois de salvar como **teste de conexão** ("broker alcançável, N tipos encontrados", ou um aviso sem bloquear). É a única forma de o gate não aceitar uma URL errada em silêncio.

---

## 3. Frontend: Login (`/login`)

- Arquivos: `features/login/login.component.{ts,html,scss}`, standalone, `FormsModule` (mesmo padrão template-driven do `natural-language.component.ts`), `OnPush`, signals para o estado (`'idle' | 'submitting' | 'error'`).
- **Layout em painel dividido** via um componente compartilhado novo, `shared/components/split-panel/split-panel.component.ts`, com `<ng-content>` para o formulário. Ele tem dois consumidores (Login e Configuração), o que justifica existir.
  - Painel de marca: fundo sólido `--color-accent` (sem gradiente), texto `#fff` (o mesmo literal já usado em `.command-form__submit`, contraste de cerca de 6:1, AA). Conteúdo: "FIWARE Conformance Auditor", uma linha de proposta de valor e uma nota "NGSI-v2 · Smart Data Models". Sem ilustração nem emoji.
  - Painel do formulário: `--color-surface`, largura máxima de 360px, labels 500, botão primário 600. Espaçamentos só com `--space-*`.
  - Abaixo de 768px as colunas empilham e o painel de marca vira uma faixa curta.
- Campos com `<label for>`, `autocomplete="username"` / `"current-password"`, `type="email"`, e o botão desabilitado durante o envio.
- Fluxo: `session.login(email, password)` → `POST /auth/login` (o `withCredentials` vem do interceptor) → em sucesso, `session.load()` → `router.navigateByUrl('/dashboard')`. **O corpo JSON da resposta é ignorado**: o sinal de sucesso é o 200 seguido do `/session` com `tenant != null`.
- Erros: 401 mostra "Email ou senha inválidos."; qualquer outro erro mostra "Não foi possível entrar. Tente novamente."

## 4. Frontend: sessão, guard e interceptor

**`core/session.service.ts`** (novo):

```ts
readonly session = signal<Session | null>(null);
load()   → GET  /session       → tap(s => this.session.set(s))
login()  → POST /auth/login    → switchMap(() => this.load())
logout() → POST /auth/logout   → tap(() => this.session.update(s => s && { ...s, tenant: null }))
```

**`core/app.guard.ts`** (novo), aplicado como `canActivate` na rota pai do shell. Roda uma vez ao entrar; a expiração durante o uso fica com o interceptor.

```ts
const cached = session.session();
return (cached?.tenant ? of(cached) : session.load()).pipe(
  map(s => s.tenant ? true : router.parseUrl(s.deployment_mode === 'saas' ? '/login' : '/config')),
  catchError(() => of(true)),  // API fora do ar: as telas já têm error-state obrigatório com retry
);
```

Como a app descobre "estou logado?" depois de um refresh: o guard chama `/session` (200 sempre, barato). Isso evita o flicker de "renderiza o shell, leva 401 e redireciona" e ainda entrega o tenant para mostrar no shell.

**`core/tenant.interceptor.ts`** (reescrito; o nome do arquivo pode continuar), só para URLs que começam com `baseUrl`:
1. `withCredentials: true` em toda chamada à API. É obrigatório no SaaS e inofensivo no self-hosted.
2. Self-hosted com `session().tenant`: anexa `Fiware-Service`/`Fiware-ServicePath` vindos da sessão, não mais da constante de build.
3. `catchError`: se for 401, o modo for `saas` **e** a URL não terminar em `/auth/login`, limpa a sessão e navega para `/login`. A exclusão do login é necessária para a tela mostrar "senha inválida" em vez de entrar em loop. No self-hosted, 401 significa header ausente, e redirecionar para `/login` estaria errado.

## 5. Frontend: gate `/config`

- `features/config/config.component.*`, também dentro de `SplitPanelComponent`. No `ngOnInit` faz `GET /config` para pré-preencher, mostrando o skeleton enquanto carrega e `ErrorStateComponent` com retry se falhar.
- Salvar: `PUT /config`, depois `session.session.set({...s, tenant})` usando o que a resposta devolve (sem refetch), depois `GET /entity-types` (seção 2.3). Se `broker_reachable`, mostra "N tipos encontrados"; se não, mostra um aviso "configuração salva, mas o broker não respondeu", com o botão "Continuar" nos dois casos, que leva a `/dashboard`.
- O bloqueio vem do `appGuard`: enquanto `tenant == null` no self-hosted, toda rota do shell cai em `/config`. `/config` fica fora do guard, para permitir reconfigurar.
- O shell ganha um link "Configuração" (só em self-hosted) e o tenant mais "Sair" (só em SaaS), lendo `session()`.

## 6. `api-config.ts` e `app.config.ts`

- `ApiConfig` fica só com `baseUrl`, que continua definido em tempo de build (correto). **O campo `tenant` e o comentário "não há tela de login" são removidos.** Os seis specs só leem `DEFAULT_API_CONFIG.baseUrl` e seguem compilando.
- `app.config.ts` não muda. O interceptor continua registrado, e `withCredentials` é por request, não por provider.
- `app.routes.ts`: `login` e `config` ficam no topo. `''` passa a ser `{ component: ShellComponent, canActivate: [appGuard], children: [...rotas atuais] }`.
- `app.component.ts`: o template vira `<router-outlet />`. O shell deixa de ser renderizado sempre, porque login e config não têm sidebar.

---

## 7. Sequenciamento: duas rodadas de TDD

O backend define o contrato (`/session`, `/config`, cookie) que o frontend consome, e cada rodada fica verde sozinha.

**Rodada 1, backend (pytest):**
1. `tests/unit/infrastructure/config/test_settings_cors.py`: rejeita `"*"` em saas e aceita em selfhosted.
2. `tests/integration/persistence/test_tenant_account_repository.py`: `get_single` com nenhuma, uma e duas linhas (`LookupError`), ignorando linhas com login.
3. `tests/unit/infrastructure/context_broker/test_self_hosted_context_broker.py` (novo, com repositório fake): com linha usa a URL e a chave da linha; sem linha usa o default; ignora o tenant.
4. `tests/unit/infrastructure/config/test_context_broker_factory.py`: self-hosted *com* chave devolve `SelfHostedContextBroker`. Os testes "sem chave" existentes ficam intactos.
5. `tests/unit/interfaces/rest/test_auth.py`:
   - o `Set-Cookie` do login tem `HttpOnly`, `Secure`, `SameSite=strict`, `Path=/`, `Max-Age=3600`, sem `Domain`, e o corpo ainda tem `access_token`;
   - `Cookie: auditor_session=<token>` leva a 200 com o tenant A; cookie inválido dá 401; Bearer ganha do cookie;
   - logout responde 204 e expira o cookie, e a rota não existe em selfhosted.
   - Atenção: o `httpx` com `base_url="http://test"` não reenvia cookies `Secure` por http, então os testes devem mandar o header `Cookie` explicitamente.
6. `tests/unit/interfaces/rest/test_session_router.py` (novo): saas sem cookie, com cookie válido e com cookie expirado; selfhosted sem chave (tenant do env), com chave e sem linha (`null`), com linha.
7. `tests/unit/interfaces/rest/test_config_router.py` (novo, com repositório fake): GET sem linha com pré-preenchimento; PUT chamando `create` e depois `replace_tenant` com `broker_api_key=None`; 422 para CRLF no service, path sem `/` e esquema `ftp://`; 404 em saas.
8. Uma linha em `selfhosted/docker-compose.yml` (serviço `app`): `CORS_ALLOWED_ORIGINS: http://localhost:5173`.

**Rodada 2, frontend (Karma headless):**
`session.service.spec.ts` → `tenant.interceptor.spec.ts` (withCredentials só para a API, headers só em self-hosted, 401 em saas redireciona, exceção do `/auth/login`) → `app.guard.spec.ts` (três ramos mais o erro) → `login.component.spec.ts` (envio, 401, botão desabilitado) → `config.component.spec.ts` (pré-preenchimento, corpo do PUT, as duas respostas do teste de conexão) → ajustar `app.component.spec.ts`.

---

## 8. Ambiguidades para você decidir

1. **JWT no corpo do login.** Mantive o token no corpo (não quebra clientes Bearer). Remover é mais estrito com o httpOnly e hoje só `test_auth.py` consome o corpo.
2. **`SESSION_COOKIE_SECURE`.** Não criei. Se o dev SaaS rodar em Safari ou num IP da LAN, o cookie `Secure` via http é descartado e a app entra em loop no `/login`. Dá para adicionar depois com default `True`.
3. **Dev em `127.0.0.1:4200`** (já liberado no `.env.example`) chamando `localhost:8000` é *cross-site*, e o cookie `Strict` não é enviado. A documentação do dev SaaS precisa dizer "use `localhost`".
4. **ADR.** Emendar a ADR-0019 (ainda "Proposto": linhas 56, 62, 108-110 e 196) ou criar uma ADR-0020 "Sessão por cookie httpOnly + gate self-hosted + `/session` em runtime no lugar da flag de build". Recomendo a ADR-0020, porque é uma decisão com alternativas próprias (localStorage, cookie legível por JS, `Domain` na raiz).
5. **`broker_api_key` no formulário self-hosted.** Fora por enquanto (seção 2.3). Confirmar que salvar pela UI pode apagar uma chave cadastrada via CLI.
6. **Homolog/academy EC2** continuam no caminho "sem chave" (só `.env`, sem gate). Se quiser o gate lá, o `user_data` precisa gerar a chave como o `fernet-keys.sh` faz.
7. **Exposição do `:8000`** no bundle (`0.0.0.0`). O PUT `/config` sem autenticação é alcançável pela LAN. Publicar em `127.0.0.1` restringe ao uso na mesma máquina.
8. **Fora do escopo, mas bloqueia o SaaS de verdade:** `DEFAULT_API_CONFIG.baseUrl = 'http://localhost:8000'` (`api-config.ts:24`) também vai na build de produção (CloudFront). O login em produção exige `https://api.<domínio>`. O domínio nunca foi registrado (`production/variables.tf:50-54`, sem default), então hoje não existe cenário cross-subdomain real para validar. Localmente é tudo `localhost`, com o mesmo site.
9. **`docker-compose.selfhosted.yml` e `Dockerfile.selfhosted` na raiz** parecem duplicatas antigas do `selfhosted/` (sem `fernet-keys.sh` nem frontend). Não mexi neles; decida se remove.
10. **Corrida em dois PUT `/config` simultâneos** sem linha ainda. Deixei sem lock; o pior caso é `IntegrityError` ou duas linhas, e o `get_single` falha alto. É aceitável para instalação de um produtor só.

---

## Arquivos afetados

| Arquivo | Mudança |
|---|---|
| `src/auditor/interfaces/rest/access_tokens.py` | `SESSION_COOKIE_NAME` |
| `src/auditor/interfaces/rest/routers/auth.py` | `set_cookie` no login; `POST /auth/logout` |
| `src/auditor/interfaces/rest/dependencies.py` | `session_token` (Bearer ou cookie); `get_tenant` usa a nova dependência |
| `src/auditor/interfaces/rest/routers/session.py` | **novo**: `GET /session` |
| `src/auditor/interfaces/rest/routers/config.py` | **novo**: `GET`/`PUT /config` (só selfhosted) |
| `src/auditor/interfaces/rest/schemas.py` | `SessionResponse`, `TenantResponse`, `BrokerConfigRequest/Response` |
| `src/auditor/interfaces/rest/app.py` | monta `session` sempre e `config` só em selfhosted |
| `src/auditor/infrastructure/config/settings.py` | validator contra `"*"` em saas |
| `src/auditor/infrastructure/config/container.py` | ramo selfhosted com/sem chave; `get_selfhosted_accounts` |
| `src/auditor/infrastructure/persistence/tenant_account_repository.py` | `get_single()` |
| `src/auditor/infrastructure/context_broker/self_hosted_context_broker.py` | **novo** |
| `selfhosted/docker-compose.yml` | `CORS_ALLOWED_ORIGINS: http://localhost:5173` |
| `frontend/src/app/core/api-config.ts` | remove `tenant` |
| `frontend/src/app/core/tenant.interceptor.ts` | withCredentials, headers vindos da sessão, 401 leva a `/login` |
| `frontend/src/app/core/session.service.ts`, `app.guard.ts` | **novos** |
| `frontend/src/app/app.routes.ts`, `app.component.ts` | rota pai do shell com guard; `login` e `config` no topo |
| `frontend/src/app/layout/shell/shell.component.ts` | link "Configuração" / tenant e "Sair" |
| `frontend/src/app/shared/components/split-panel/` | **novo** |
| `frontend/src/app/features/login/`, `features/config/` | **novos** |
| `docs/adr/adr-0020.md` (ou emenda na 0019) | registro da decisão |
| Testes | ver seção 7 |

### Critical Files for Implementation
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/rest/dependencies.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/rest/routers/auth.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/container.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/frontend/src/app/core/tenant.interceptor.ts
