# Plano: autenticação JWT, `deployment_mode` e `audit tenant register` (ADR-0019)

Conferi todas as premissas contra o código espelhado em `/mnt/user-data/uploads/agent_multi_IA_context_broker`. Três delas o próprio código corrige: o nome da variável do segredo, a grafia do modo self-hosted e a origem do tenant no self-hosted. Estão na seção 0.

---

## 0. Premissas confirmadas e corrigidas

| # | Premissa do pedido | O que o código mostra | Decisão |
|---|---|---|---|
| 1 | Campo `jwt_secret_key` | A infra já usa **`JWT_SIGNING_KEY`**. `interfaces/aws_lambda/_bootstrap.py:40-43` popula `os.environ["JWT_SIGNING_KEY"]` a partir do Parameter Store, e `infra/terraform/modules/parameter_store/main.tf:39` cria `/<prefix>/jwt-signing-key`. | O campo passa a se chamar **`jwt_signing_key: SecretStr \| None`**. Com `jwt_secret_key`, o Lambda de produção escreveria uma variável que ninguém lê. |
| 2 | Valores `"saas"` / `"self_hosted"` | A ADR-0019 §4 fixa `"saas" \| "selfhosted"`, sem underscore, com default `"selfhosted"`. O `.env.example` e o `.env` não têm `DEPLOYMENT_MODE`, então o valor implícito hoje é self-hosted. | `Literal["saas", "selfhosted"] = "selfhosted"`. |
| 3 | Self-hosted mantém o comportamento atual (headers) | A ADR §1 diz que em self-hosted "o tenant continua vindo de `Settings.fiware_service`/`fiware_service_path`". O código atual lê os headers. | Segui o pedido: self-hosted fica **idêntico ao atual** (headers). A divergência com a ADR está no item R3. |
| 4 | Busca por email | Confirmado: não existe. O repositório só tem `create`, `get_by_tenant`, `update_broker`, `replace_tenant` e `rotate_encryption`. A tabela tem `UniqueConstraint("login_email", name="uq_tenant_accounts_login_email")` e `CHECK (login_email IS NULL) = (password_hash IS NULL)`, e `create` já normaliza com `strip().lower()`. | Método novo `get_by_login_email`, com a normalização extraída para uma função única compartilhada com `create`. |
| 5 | Lib de JWT | Nem `pyjwt` nem `python-jose` aparecem no `pyproject.toml` ou no `requirements.txt`. No sandbox, o Python do sistema tem **PyJWT 2.12.1** (não declarado), `jose` não existe e o PyPI responde (`pip index versions pyjwt`, última versão 2.15.0). Os venvs `/tmp/tcc-venv` e `/tmp/venv_test` estão desatualizados: não têm nem `bcrypt`. | Usar **PyJWT** e declarar a **dependência nova** `pyjwt>=2.8.0` nos dois arquivos. Validei na 2.12.1 a API usada: `jwt.encode`, `jwt.decode(algorithms=[...], options={"require": [...]})`, `alg=none` rejeitado com `InvalidAlgorithmError`, `ExpiredSignatureError`, `MissingRequiredClaimError`. Todas são subclasses de `jwt.InvalidTokenError`. |
| 6 | Parser do header `Authorization` | FastAPI 0.141.1 (venv): `HTTPBearer(auto_error=False)` devolve `None` quando o header está ausente, o esquema não é `bearer` ou as credenciais estão vazias. | Uso o `HTTPBearer` nativo em vez de um parser manual. |
| 7 | Padrão de erro no CLI | `except Exception as exc: typer.echo(f"...{exc}")`. **Achado:** `str(IntegrityError)` inclui `[parameters: ...]` (confirmado no SQLAlchemy 2.0.53), ou seja, `password_hash` e a api key cifrada. E um erro de CHECK do Postgres traz `DETAIL: Failing row contains (...)` com a linha inteira. | No `register`, `IntegrityError` nunca é impresso cru: vira uma mensagem mapeada pelo nome da constraint. Somo `hide_parameters=True` no engine (seção 1.9). |
| 8 | bcrypt com mais de 72 bytes | `hash_password` já recusa mais de 72 bytes. `verify_password` não tem guarda: no bcrypt 5.x o `checkpw` tende a lançar `ValueError` (daria 500 no login) e no 4.x trunca. | Guarda em `verify_password`: acima de 72 bytes retorna `False`. É correto porque nenhum hash armazenado vem de senha com mais de 72 bytes. |
| 9 | Padrão de teste de router | `create_app()` + `app.dependency_overrides[...]` + `httpx.ASGITransport`. O override de função com `@lru_cache` já funciona (`get_engine` em `test_health_router.py`). | Mesmo padrão, com override de `get_settings` e `get_tenant_account_repository`. |
| 10 | Padrão de teste de CLI | `monkeypatch.setattr(cli_main, "get_tenant_account_repository", ...)` + `CliRunner`. | Mesmo padrão. |

---

## 1. Arquivos e esquema exato de cada mudança

### Alterados
- `pyproject.toml` e `requirements.txt`: dependência nova `pyjwt>=2.8.0`.
- `src/auditor/infrastructure/config/settings.py`: 3 campos + 1 validador.
- `src/auditor/infrastructure/config/container.py`: `hide_parameters=True` em `get_engine`.
- `src/auditor/infrastructure/persistence/tenant_account_repository.py`: `_normalize_email`, `get_by_login_email`, `_to_account` e a guarda em `verify_password`.
- `src/auditor/interfaces/rest/schemas.py`: `LoginRequest` e `AccessTokenResponse`.
- `src/auditor/interfaces/rest/dependencies.py`: ramificação de `get_tenant` e correção da docstring desatualizada.
- `src/auditor/interfaces/rest/app.py`: `include_router(auth.router)` só em SaaS.
- `src/auditor/interfaces/cli/main.py`: `tenant register`.
- `.env.example`: `DEPLOYMENT_MODE`, `JWT_SIGNING_KEY`, `JWT_EXPIRATION_MINUTES`.

### Novos
- `src/auditor/interfaces/rest/access_tokens.py`: encode e decode num só lugar, para algoritmo e claims não poderem divergir entre quem emite e quem valida.
- `src/auditor/interfaces/rest/routers/auth.py`
- `tests/unit/infrastructure/config/test_settings_auth.py`
- `tests/unit/interfaces/rest/test_auth.py`

### 1.1 `settings.py`

```python
from typing import Literal

from pydantic import Field, SecretStr, model_validator

    deployment_mode: Literal["saas", "selfhosted"] = "selfhosted"
    jwt_signing_key: SecretStr | None = None
    jwt_expiration_minutes: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def _require_jwt_signing_key_in_saas(self) -> "Settings":
        if self.deployment_mode == "saas" and (
            self.jwt_signing_key is None
            or len(self.jwt_signing_key.get_secret_value().encode("utf-8")) < 32
        ):
            raise ValueError("DEPLOYMENT_MODE=saas exige JWT_SIGNING_KEY com pelo menos 32 bytes")
        return self
```

Esse fail-fast é mais forte que o das chaves Fernet, que só falha quando a factory é chamada. Aqui quem falha é o próprio `Settings()`, e `create_app()` chama `get_settings()` no import (por causa do CORS). Um deploy SaaS sem chave, ou com o placeholder `REPLACE_AFTER_APPLY` do Terraform (18 bytes), não sobe. O mínimo de 32 bytes segue a RFC 7518 §3.2; a própria PyJWT 2.12 emite `InsecureKeyLengthWarning` abaixo disso. Em self-hosted a chave continua opcional. Validei o comportamento no pydantic 2.13.5 / pydantic-settings 2.15.0.

### 1.2 `access_tokens.py` (novo)

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.settings import Settings

JWT_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["exp", "fiware_service", "fiware_service_path"]


def _signing_key(settings: Settings) -> str:
    if settings.jwt_signing_key is None:
        raise RuntimeError("JWT_SIGNING_KEY nao configurada")
    return settings.jwt_signing_key.get_secret_value()


def issue_access_token(tenant: Tenant, settings: Settings) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    return jwt.encode(
        {
            "fiware_service": tenant.fiware_service,
            "fiware_service_path": tenant.fiware_service_path,
            "exp": expires_at,
        },
        _signing_key(settings),
        algorithm=JWT_ALGORITHM,
    )


def tenant_from_access_token(token: str, settings: Settings) -> Tenant:
    claims = jwt.decode(
        token,
        _signing_key(settings),
        algorithms=[JWT_ALGORITHM],
        options={"require": _REQUIRED_CLAIMS},
    )
    service, path = claims["fiware_service"], claims["fiware_service_path"]
    if not isinstance(service, str) or not isinstance(path, str):
        raise jwt.InvalidTokenError("claims de tenant com tipo invalido")
    return Tenant(fiware_service=service, fiware_service_path=path)
```

**Regras de segurança da implementação:**
- `algorithms=[JWT_ALGORITHM]` é uma lista fixa com um único item. Isso rejeita `alg=none`, `HS512`/`HS384` assinados com a mesma chave e qualquer confusão de algoritmo.
- **Proibido:** `options={"verify_signature": False}`, `verify_exp: False`, `jwt.get_unverified_header` para escolher o algoritmo, `algorithms=None`, ou qualquer leitura de claims antes do `decode` verificado.
- `exp` é obrigatório via `require`. Sem isso, um token sem `exp` seria eterno, porque a PyJWT só valida `exp` quando ele existe. O leeway padrão é 0.
- `require` só barra claims ausentes (`None`). Tipo errado é barrado pelo `isinstance`, e string vazia pelo `InvalidTenantError` do próprio `Tenant`.

### 1.3 `dependencies.py`

```python
import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auditor.domain.errors import InvalidTenantError
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_settings
from auditor.infrastructure.config.settings import Settings
from auditor.interfaces.rest.access_tokens import tenant_from_access_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_tenant(
    fiware_service: str | None = Header(default=None, alias="Fiware-Service"),
    fiware_service_path: str = Header(default="/", alias="Fiware-ServicePath"),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Tenant:
    if settings.deployment_mode == "saas":
        if credentials is None:
            raise _unauthorized("Token Bearer obrigatorio.")
        try:
            return tenant_from_access_token(credentials.credentials, settings)
        except (jwt.InvalidTokenError, InvalidTenantError):
            raise _unauthorized("Token invalido ou expirado.") from None
    # (bloco self-hosted atual, sem nenhuma mudança)
```

- Em SaaS, os headers `Fiware-Service`/`Fiware-ServicePath` são declarados mas nunca lidos: o tenant só pode vir do token assinado.
- A mensagem de 401 é a mesma para token expirado, com assinatura errada ou malformado. O cliente não descobre qual verificação falhou.
- A docstring do módulo tem hoje a frase "Auth completa (JWT) e' escopo de fase posterior", que deixa de ser verdade. Ela é trocada por uma frase curta e verdadeira. Nenhum comentário novo.
- Não há import circular: `container` não importa nada de `interfaces`.

### 1.4 `schemas.py`

```python
class LoginRequest(BaseModel):
    login_email: str
    password: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

`str` em vez de `EmailStr`: `email-validator` não está instalado nem declarado, e o repositório já normaliza.

### 1.5 `routers/auth.py` (novo)

```python
from __future__ import annotations

import asyncio
import secrets
from functools import cache

from fastapi import APIRouter, Depends, HTTPException, status

from auditor.infrastructure.config.container import get_settings, get_tenant_account_repository
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import (
    TenantAccountRepository,
    hash_password,
    verify_password,
)
from auditor.interfaces.rest.access_tokens import issue_access_token
from auditor.interfaces.rest.schemas import AccessTokenResponse, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@cache
def _dummy_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def _password_matches(password: str, password_hash: str | None) -> bool:
    return verify_password(password, password_hash or _dummy_password_hash())


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
    repository: TenantAccountRepository = Depends(get_tenant_account_repository),
) -> AccessTokenResponse:
    account = await repository.get_by_login_email(body.login_email)
    password_ok = await asyncio.to_thread(
        _password_matches, body.password, account.password_hash if account else None
    )
    if account is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha invalidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AccessTokenResponse(access_token=issue_access_token(account.tenant, settings))
```

- O hash fictício faz um email inexistente gastar o mesmo custo de bcrypt que uma senha errada. Sem isso, o tempo de resposta revelaria se o email existe.
- `asyncio.to_thread`: o bcrypt leva cerca de 250 ms de CPU. Rodando direto no event loop, cada login congelaria a API inteira, o que amplificaria um DoS.
- O `@cache` faz o primeiro login com email inexistente pagar um hash a mais, uma única vez por processo. Isso é aceitável.

### 1.6 `app.py`

```python
from auditor.interfaces.rest.routers import audits, auth, catalog, entity_types, health
...
    if get_settings().deployment_mode == "saas":
        app.include_router(auth.router)
```

Em self-hosted a rota não existe (404), como a ADR §2 pede ("a rota de login não existe"). Isso também evita um 500 quando as chaves Fernet estão ausentes. O CORS não precisa mudar: `allow_headers=["*"]` já cobre `Authorization`.

### 1.7 `tenant_account_repository.py`

```python
from sqlalchemy import RowMapping, func, select


def _normalize_email(login_email: str) -> str:
    return login_email.strip().lower()


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("ascii"))
```

- Em `create`: `normalized_email = _normalize_email(login_email) if login_email is not None else None`.
- `get_by_tenant` passa a terminar com `return self._to_account(row) if row is not None else None`, e o corpo de mapeamento atual sai dali para `_to_account`.

```python
    async def get_by_login_email(self, login_email: str) -> TenantAccount | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(tenant_accounts_table).where(
                        tenant_accounts_table.c.login_email == _normalize_email(login_email)
                    )
                )
            ).mappings().first()
        return self._to_account(row) if row is not None else None

    def _to_account(self, row: RowMapping) -> TenantAccount:
        decrypted_api_key = (
            self._fernet.decrypt(row["broker_api_key_encrypted"].encode("ascii")).decode("utf-8")
            if row["broker_api_key_encrypted"] is not None
            else None
        )
        return TenantAccount(
            tenant=Tenant(
                fiware_service=row["fiware_service"],
                fiware_service_path=row["fiware_service_path"],
            ),
            broker_url=row["broker_url"],
            broker_api_key=decrypted_api_key,
            login_email=row["login_email"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
```

A busca usa o índice da unique constraint. `RowMapping` é importável do topo do `sqlalchemy` (conferido na 2.0.53).

### 1.8 `cli/main.py`: `audit tenant register`

```python
import secrets
from sqlalchemy.exc import IntegrityError

_REGISTER_CONSTRAINT_MESSAGES = {
    "pk_tenant_accounts": "ja existe conta para este Fiware-Service/Fiware-ServicePath",
    "uq_tenant_accounts_login_email": "este email ja esta em uso",
}


@tenant_app.command("register")
def tenant_register(
    tenant: str = typer.Option(..., "--tenant", help="Fiware-Service."),
    service_path: str = typer.Option("/", "--service-path", help="Fiware-ServicePath."),
    broker_url: str = typer.Option(..., "--broker-url", help="URL do Orion do tenant."),
    broker_api_key: str = typer.Option(None, "--broker-api-key", help="Api key do broker (cifrada em repouso)."),
    email: str = typer.Option(None, "--email", help="Login SaaS (omitir = conta self-hosted, sem login)."),
    password: str = typer.Option(None, "--password", help="Senha inicial (omitida com --email = gerada e exibida uma unica vez)."),
) -> None:
    """Cadastra uma conta em tenant_accounts (ADR-0019)."""
    if password is not None and (email is None or not password):
        typer.echo("--password exige --email e nao pode ser vazia.", err=True)
        raise typer.Exit(code=1)
    generated_password = secrets.token_urlsafe(16) if email is not None and password is None else None

    async def _register() -> None:
        await get_tenant_account_repository().create(
            Tenant(fiware_service=tenant, fiware_service_path=service_path),
            broker_url=broker_url,
            broker_api_key=broker_api_key,
            login_email=email,
            password=password if password is not None else generated_password,
        )

    try:
        asyncio.run(_register())
    except IntegrityError as exc:
        reason = next(
            (msg for name, msg in _REGISTER_CONSTRAINT_MESSAGES.items() if name in str(exc.orig)),
            "restricao do banco violada",
        )
        typer.echo(f"Erro ao registrar tenant: {reason}.", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Erro ao registrar tenant: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Conta registrada: {tenant} {service_path}")
    if generated_password is not None:
        typer.echo(f"Senha inicial (exibida uma unica vez): {generated_password}")
```

- `IntegrityError` **nunca** é impresso inteiro: vazaria `[parameters: ...]` e o `DETAIL: Failing row contains` com o `password_hash`.
- Uma senha passada por `--password` nunca é ecoada. Gerar a senha quando ela é omitida segue a ADR ("devolve em texto puro uma única vez") e evita que ela fique no histórico do shell.

### 1.9 `container.get_engine`

```python
return create_async_engine(get_settings().database_url, hide_parameters=True)
```

É a correção na raiz: nenhum traceback ou log de qualquer `DBAPIError` (login, register, genérico) passa a mostrar parâmetros SQL como hash, api key cifrada ou email.

### 1.10 `.env.example`

- `DEPLOYMENT_MODE=selfhosted`
- `JWT_SIGNING_KEY=`, com a dica de geração `python -c "import secrets; print(secrets.token_urlsafe(48))"` e o aviso de que é obrigatória com pelo menos 32 bytes em `saas`.
- `JWT_EXPIRATION_MINUTES=60`

---

## 2. Sequência TDD

**Passo 0 (pré-requisito, sem Docker):** declarar `pyjwt>=2.8.0` e rodar `pip install -e ".[dev]"` no ambiente onde a suíte roda. O ambiente que rodou as rodadas anteriores não é este sandbox (aqui não há `bcrypt`). Depois, suíte atual verde como baseline.

### Sem Docker

1. **Settings.** Novo `tests/unit/infrastructure/config/test_settings_auth.py`, sempre com `Settings(_env_file=None, ...)`:
   - vermelho: default `"selfhosted"`;
   - `saas` sem chave levanta `ValidationError`;
   - `saas` com `"REPLACE_AFTER_APPLY"` (curta) levanta `ValidationError`;
   - `saas` com 32 bytes funciona;
   - `selfhosted` sem chave funciona;
   - `deployment_mode="bogus"` levanta `ValidationError`;
   - `jwt_expiration_minutes=0` levanta `ValidationError`;
   - a chave não aparece em `repr`.

   Verde com a seção 1.1.
2. **`verify_password`.** Em `tests/unit/infrastructure/persistence/test_tenant_account_passwords.py`, vermelho: `verify_password("ã"*37, hash_password("x"))` retorna `False` sem exceção. Verde com a guarda.
3. **`hide_parameters`.** Um assert em `test_tenant_account_repository_factory.py` (o arquivo que já limpa os caches): `container_module.get_engine().sync_engine.hide_parameters is True`, com `get_engine.cache_clear()` no fixture. Verde com a seção 1.9.
4. **`get_tenant` em SaaS.** Novo `tests/unit/interfaces/rest/test_auth.py`.
   - Fixture: `_SAAS = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k"*32)`, um `_RecordingBroker` com `list_entity_types(tenant)` que grava o tenant, e um helper que faz `monkeypatch.setattr(app_module, "get_settings", lambda: _SAAS)`, chama `app_module.create_app()` e aplica `dependency_overrides[get_settings]`, `[get_context_broker]` e `[get_tenant_account_repository]`.
   - Vermelho: os casos de borda B1 a B11 da seção 3 via `GET /entity-types`.
   - Verde com as seções 1.2 e 1.3.
5. **Regressão self-hosted.** No mesmo arquivo:
   - B12: `Authorization: Bearer <lixo>` junto com headers retorna 200 com o tenant dos headers;
   - B13: `POST /auth/login` retorna 404.

   Os testes existentes (`test_missing_tenant_header_returns_401` etc.) ficam intactos e verdes.
6. **Login.** Fake com `get_by_login_email` que devolve um `TenantAccount` com `hash_password("senha-correta")`. Vermelho: L1 a L6 da seção 3. Verde com as seções 1.4, 1.5 e 1.6.
7. **CLI register.** Em `tests/unit/interfaces/cli/test_cli.py`, `_FakeTenantAccountRepository` ganha `create(...)`, que grava os argumentos ou levanta o erro configurado. A exceção de teste é `IntegrityError("INSERT", {"password_hash": "SEGREDO"}, Exception('duplicate key value violates unique constraint "pk_tenant_accounts"'))`. Vermelho: C1 a C7. Verde com a seção 1.8.

### Com Postgres (testcontainers, `-m integration`)

8. **`get_by_login_email`.** Nova classe `TestGetByLoginEmail` em `tests/integration/persistence/test_tenant_account_repository.py`:
   - devolve a conta certa, com `tenant == TENANT_A` e `verify_password` ok, entre duas contas SaaS;
   - `"  Tenant@Example.COM "` encontra a conta gravada como `tenant@example.com`;
   - email desconhecido devolve `None`;
   - com uma conta self-hosted (`login_email NULL`) presente, `get_by_login_email("")` devolve `None`.

   Os testes existentes de `get_by_tenant` provam que o refactor de `_to_account` não mudou nada.
9. **Suíte completa**, unitária e de integração.

---

## 3. Casos de borda de segurança (cada um é um teste)

**`get_tenant` em SaaS** (todos devem dar **401** com `WWW-Authenticate: Bearer`, exceto B10 e B11):

| # | Caso |
|---|---|
| B1 | Sem header `Authorization`, com `Fiware-Service` presente. Os headers não salvam a requisição. |
| B2 | `Authorization: Basic abc`. |
| B3 | Token malformado (`Bearer abc`). |
| B4 | Token expirado: `exp` no passado, assinado com a chave certa. |
| B5 | Assinatura errada: outra chave de 32 bytes. |
| B6 | `alg=none`: `jwt.encode(payload, None, algorithm="none")`. |
| B7 | `HS512` com a mesma chave (fixação de algoritmo). |
| B8 | Sem `exp` (token eterno) e, em outro teste, sem `fiware_service`. |
| B9 | `fiware_service: ""` e `fiware_service: 123`. |
| B10 | Token do tenant A com headers `Fiware-Service: B` → **200**, e o broker recebe o tenant **A**. |
| B11 | Ida e volta real: `POST /auth/login` e depois `GET /entity-types` com o token → o broker recebe o tenant da conta. `exp` fica entre agora + 59 e agora + 61 min. |

**Self-hosted:**
- B12: o header `Authorization` é ignorado e o tenant vem dos headers.
- B13: `/auth/login` retorna 404.

**Login:**

| # | Caso | Esperado |
|---|---|---|
| L1 | Credenciais certas | 200, `token_type == "bearer"`, o token decodifica para o tenant da conta. |
| L2 | Senha errada | 401. |
| L3 | Email inexistente | 401, com **JSON idêntico** ao de L2. |
| L4 | Email inexistente | O fake confirma que `_password_matches` rodou (verifica o caminho do hash fictício, não o tempo). |
| L5 | Senha com mais de 72 bytes | 401, não 500. |
| L6 | Corpo sem `password` | 422. |

**Acesso a dados de outro tenant:** B10 prova que o tenant só vem do token. O filtro por tenant no repositório já está coberto por `test_run_belonging_to_another_tenant_returns_404_not_403` (`test_audits_router.py`). Juntos, os dois fecham o caso sem duplicar a infraestrutura de fakes de audits.

**CLI:**

| # | Caso |
|---|---|
| C1 | SaaS com `--email` e `--password`: exit 0, `create` recebe os argumentos, e a senha **não** aparece no stdout. |
| C2 | `--email` sem `--password`: a senha gerada aparece uma vez e é a mesma passada a `create`. |
| C3 | Sem `--email`: `create` recebe `login_email=None` e `password=None`, e nenhuma linha de senha é impressa. |
| C4 | `--password` sem `--email`, ou `--password ""`: exit diferente de 0 e `create` nunca é chamado. |
| C5 | Tenant duplicado: exit diferente de 0, a mensagem contém "ja existe conta", e **nem** `"SEGREDO"` **nem** `Traceback` aparecem na saída. |
| C6 | Email duplicado: mensagem "email ja esta em uso". |
| C7 | `RuntimeError` genérico: exit diferente de 0 e sem traceback. |

---

## 4. Ambiguidades residuais

- **R1 (nome da variável):** `jwt_signing_key` / `JWT_SIGNING_KEY` no lugar de `jwt_secret_key`, para casar com o Lambda e o Terraform já existentes. É preciso confirmar se esse nome é aceitável.
- **R2 (grafia):** `"selfhosted"` segue a ADR. Se preferir `self_hosted`, a ADR precisa mudar junto.
- **R3 (origem do tenant no self-hosted):** a ADR §1 diz que o tenant vem de `Settings`; este plano mantém os headers, como foi pedido. Para seguir a ADR, basta trocar o bloco self-hosted para `Tenant(settings.fiware_service, settings.fiware_service_path)`. Isso quebra `test_missing_tenant_header_returns_401` de propósito, e o frontend atual já manda os headers.
- **R4 (o que o CLI gera):** a ADR diz que `register` gera a **api_key** e a senha. O plano só gera a senha, quando omitida. A api key continua vindo de `--broker-api-key`, como foi pedido.
- **R5 (SSE no SaaS):** o `EventSource` do navegador não envia `Authorization`, então `GET /audits/{id}/stream` quebra no SaaS. A correção é no frontend (SSE via `fetch` ou polling de `/progress`), não no backend. Token em query string está **descartado**, porque vaza em logs de acesso.
- **R6 (revogação de tokens):** não há refresh, logout nem revogação. O `plano_refatoracao_v3.md:470` cita "refresh", a ADR-0019 não. Consequência: trocar a senha ou apagar a conta **não** invalida tokens já emitidos até o `exp` (60 min).
- **R7 (força bruta):** não há rate limiting nem bloqueio de conta em `/auth/login`. A ADR não trata do assunto; fica registrado como risco aceito.
- **R8 (broker por tenant):** `get_context_broker()` continua usando `Settings.fiware_broker_url`. Depois deste plano, o SaaS autentica o tenant certo mas ainda consulta o broker global. Resolver `broker_url`/`api_key` pela conta é o próximo passo da ADR.
- **R9 (decifrar no login):** `get_by_login_email` decifra a api key sem necessidade para o login. Se alguma linha não decifrar (rotação mal feita), o login dá 500. A alternativa é um select só de tenant e hash, mas fica fora do diff mínimo.
- **R10 (`.env` nos testes):** os testes de router usam o `get_settings()` real, que lê o `.env`. Se o `.env` local de algum dev tiver `DEPLOYMENT_MODE=saas`, os testes existentes quebram. Hoje o `.env` não tem a variável.
- **R11 (atualizar a ADR):** a §4 da ADR-0019 diz "Ainda não implementado" e, na §1, os valores de `deployment_mode`. Vale atualizar depois da implementação.

---

### Arquivos críticos para a implementação
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/rest/dependencies.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/settings.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/cli/main.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/rest/app.py`

Arquivos novos: `src/auditor/interfaces/rest/access_tokens.py` e `src/auditor/interfaces/rest/routers/auth.py`.
