# Plano: tabela `tenant_accounts` + migration + `TenantAccountRepository` (ADR-0019, seção 1)

## 0. Duas premissas do pedido que o código não confirma

- **A última migration não é `0cfa66a23db8`.** A cadeia real, lida nos `revision`/`down_revision`, é:
  `2f62abb9e945` (inicial) → `42889f2ad3cf` → `0cfa66a23db8` → `d04e459a57d1` → **`92150912594b`** (head atual, de 2026-09-14). A nova migration encadeia em `92150912594b`.
- **Não existe teste de repositório em `tests/unit/infrastructure/persistence/`.** Lá só há `test_mappers.py`, que testa mapeamento puro, sem banco. Todos os testes de repositório e tabela ficam em `tests/integration/` e usam testcontainers (`PostgresContainer("pgvector/pgvector:pg16")`, marker `integration`, precisam de Docker). O plano segue esse padrão.
- **Tensão de estilo:** o código existente comenta muito o "porquê" (cita ADRs e specs em toda parte). O código novo fica **sem comentários**, por instrução do dono do projeto. Isso é intencional, não um descuido.

## 1. Arquivos novos e alterados

| Ação | Caminho |
|---|---|
| alterar | `/mnt/user-data/uploads/agent_multi_IA_context_broker/pyproject.toml` (deps `cryptography`, `bcrypt`) |
| alterar | `/mnt/user-data/uploads/agent_multi_IA_context_broker/requirements.txt` (mesmas deps; o `Dockerfile` do Lambda instala a partir daqui, e o `selfhosted/Dockerfile` usa `pip install -e .`, então os dois arquivos precisam ser alterados) |
| alterar | `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tables.py` (novo `tenant_accounts_table` no `metadata` existente) |
| novo | `/mnt/user-data/uploads/agent_multi_IA_context_broker/migrations/versions/edfd0898f739_add_tenant_accounts_table.py` |
| novo | `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py` |
| alterar | `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/settings.py` (campo da chave) |
| alterar | `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/container.py` (factory `get_tenant_account_repository`) |
| alterar | `/mnt/user-data/uploads/agent_multi_IA_context_broker/.env.example` (`BROKER_API_KEY_ENCRYPTION_KEY=`) |
| novo | `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/persistence/test_tenant_account_passwords.py` |
| novo | `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/config/test_tenant_account_repository_factory.py` |
| novo | `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/persistence/test_tenant_account_repository.py` |
| alterar | `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/persistence/test_migrations.py` (`EXPECTED_TABLES` + 2 testes de constraint) |

`migrations/env.py` **não muda**: ele já importa o `metadata` de `persistence/tables.py`.

## 2. Dependências novas (verificadas)

Nenhuma das duas está declarada em `pyproject.toml` nem em `requirements.txt`. No `grep`, não aparece `fernet`, `bcrypt`, `passlib` nem `encrypt` em `src/`. Não existe hoje nenhum padrão de criptografia em repouso no repositório.

- `cryptography>=42.0.0`. Aparece instalada no sandbox (46.0.7), só como dependência transitiva. Mesmo assim, declarar explicitamente.
- `bcrypt>=4.1.0`. Não está instalada. Usar `bcrypt` direto, **não `passlib`**: o passlib não é mantido e quebra com bcrypt 4.1 ou mais novo.

APIs reais que serão usadas:
- `from cryptography.fernet import Fernet, InvalidToken`
- `Fernet.generate_key()`, `Fernet(key).encrypt(bytes) -> bytes`, `.decrypt(bytes) -> bytes`
- `bcrypt.hashpw(pw_bytes, bcrypt.gensalt()) -> bytes`, `bcrypt.checkpw(pw_bytes, hash_bytes) -> bool`

## 3. Criptografia: decisão

- **Fernet** (AES-128-CBC + HMAC-SHA256, com autenticação). É simétrico, uma linha para cifrar e outra para decifrar, e o token é ASCII em base64 url-safe. Por isso cabe numa coluna `String`, sem `LargeBinary`.
- **Origem da chave:** novo campo em `Settings`:
  `broker_api_key_encryption_key: SecretStr | None = None` (`from pydantic import SecretStr`). A variável de ambiente é `BROKER_API_KEY_ENCRYPTION_KEY`. `SecretStr` evita que a chave apareça em `repr`/logs; não há precedente de `SecretStr` no `Settings` atual, mas é uma medida de segurança e não deve ser simplificada.
- **Container:** mesmo padrão de `get_catalog_sync_status_repository`, com `@lru_cache`, e o mesmo padrão de erro de `get_job_queue` (`RuntimeError` quando falta configuração obrigatória):
  ```python
  @lru_cache
  def get_tenant_account_repository() -> TenantAccountRepository:
      key = get_settings().broker_api_key_encryption_key
      if key is None:
          raise RuntimeError("BROKER_API_KEY_ENCRYPTION_KEY nao configurada")
      return TenantAccountRepository(get_engine(), Fernet(key.get_secret_value()))
  ```
  Nenhum caller existente passa a chamar essa factory, então não há regressão.
- **Senha:** bcrypt via duas funções de módulo em `tenant_account_repository.py`: `hash_password(password: str) -> str` e `verify_password(password: str, password_hash: str) -> bool`. `hash_password` levanta `ValueError` se `len(password.encode("utf-8")) > 72`. Motivo: o bcrypt 4.x trunca em silêncio e o 5.x levanta erro; a checagem explícita dá o mesmo comportamento nas duas versões.

## 4. Tabela `tenant_accounts`

Em `tables.py`, no estilo **SQLAlchemy Core** (`Table(..., metadata, Column(...))`), que é o estilo realmente usado no arquivo (não há ORM declarativo). Colunas:

| coluna | tipo | restrições |
|---|---|---|
| `fiware_service` | `String` | `NOT NULL`, PK (parte 1) |
| `fiware_service_path` | `String` | `NOT NULL`, PK (parte 2) |
| `broker_url` | `String` | `NOT NULL` |
| `broker_api_key` | `String` | `NULL` (token Fernet, nunca texto puro; nulo no self-hosted, onde a ADR-0019 §2 diz "sem `api_key`") |
| `login_email` | `String` | `NULL`, `UNIQUE` (o Postgres aceita vários NULLs num UNIQUE) |
| `password_hash` | `String` | `NULL` |
| `created_at` | `DateTime(timezone=True)` | `NOT NULL`, `server_default=text("now()")` |
| `updated_at` | `DateTime(timezone=True)` | `NOT NULL`, `server_default=text("now()")` |

Constraints com nome:
- `PrimaryKeyConstraint("fiware_service", "fiware_service_path", name="pk_tenant_accounts")`. A chave natural como PK tem precedente: `knowledge_chunks.chunk_id`, "não um uuid gerado".
- `UniqueConstraint("login_email", name="uq_tenant_accounts_login_email")`
- `CheckConstraint("(login_email IS NULL) = (password_hash IS NULL)", name="ck_tenant_accounts_login_pair")`: login fica todo preenchido (SaaS) ou todo vazio (self-hosted).
- `CheckConstraint("broker_url <> ''", name="ck_tenant_accounts_broker_url_not_empty")`
- Não precisa de índice extra: a busca por tenant usa a PK, e a busca futura por email usa o índice que o UNIQUE já cria. O índice HNSW de `knowledge_chunks` não tem análogo aqui.

Os imports que `tables.py` precisa acrescentar são `CheckConstraint` e `PrimaryKeyConstraint`. `text` e `DateTime` já são importados.

## 5. Migration

Arquivo `migrations/versions/edfd0898f739_add_tenant_accounts_table.py`, escrita à mão no mesmo formato de `d04e459a57d1`/`92150912594b`:
- docstring com título, `Revision ID: edfd0898f739`, `Revises: 92150912594b`, `Create Date: 2026-09-26`
- `revision: str = "edfd0898f739"`
- `down_revision: Union[str, None] = "92150912594b"`
- `branch_labels`/`depends_on = None`
- `upgrade()`: um `op.create_table("tenant_accounts", ...)` com as mesmas colunas e constraints da seção 4 (`sa.String()`, `sa.DateTime(timezone=True)`, `server_default=sa.text("now()")`, `sa.PrimaryKeyConstraint(...)`, `sa.UniqueConstraint(...)`, `sa.CheckConstraint(...)`)
- `downgrade()`: `op.drop_table("tenant_accounts")`

O ID `edfd0898f739` foi gerado com `uuid4().hex[:12]`. Qualquer hex de 12 caracteres único serve.

## 6. API do repositório (`tenant_account_repository.py`)

```python
@dataclass(frozen=True)
class TenantAccount:
    tenant: Tenant                 # auditor.domain.value_objects.tenant.Tenant (existe)
    broker_url: str
    broker_api_key: str | None     # já decifrada
    login_email: str | None
    password_hash: str | None
    created_at: datetime
    updated_at: datetime

class TenantAccountRepository:
    def __init__(self, engine: AsyncEngine, fernet: Fernet) -> None
    async def create(self, tenant: Tenant, broker_url: str, broker_api_key: str | None = None,
                     login_email: str | None = None, password: str | None = None) -> None
    async def get_by_tenant(self, tenant: Tenant) -> TenantAccount | None
    async def update_broker(self, tenant: Tenant, broker_url: str, broker_api_key: str | None) -> None
```

- `create` cifra a `broker_api_key` (quando não é None), chama `hash_password(password)` (quando não é None) e faz um único `insert`. Uma PK ou email duplicado propaga `sqlalchemy.exc.IntegrityError` sem tradução, como já faz `test_migrations.py::test_duplicate_chunk_id_insert_is_rejected_by_primary_key`.
- `get_by_tenant`: `select ... where` nas duas partes da PK, com `.mappings().first()`, no mesmo estilo de `CatalogSyncStatusRepository.get`.
- `update_broker`: `update ... values(broker_url, broker_api_key cifrada, updated_at=func.now())`. Se `result.rowcount == 0`, levanta `LookupError`. Um no-op silencioso esconderia uma configuração que não foi salva.
- Não entram agora: troca de senha, busca por email e upsert. Entram junto com `audit tenant register` e `POST /auth/login`.

## 7. Sequência TDD (teste primeiro, depois o código mínimo que o faz passar)

**Fase A: unitário, sem Docker. Roda com `pytest tests/unit/infrastructure/persistence/test_tenant_account_passwords.py tests/unit/infrastructure/config/test_tenant_account_repository_factory.py`**

1. `test_hash_password_never_returns_the_plaintext_and_is_bcrypt`: o hash é diferente da senha e começa com `"$2b$"`. Implementação: `hash_password` e as deps novas.
2. `test_verify_password_accepts_the_correct_password`: `verify_password(pw, hash_password(pw)) is True`. Implementação: `verify_password`.
3. `test_verify_password_rejects_a_wrong_password`: retorna `False`.
4. `test_hash_password_rejects_more_than_72_utf8_bytes`: `"ã" * 37` (37 caracteres, 74 bytes) levanta `ValueError`, e `"ã" * 36` (72 bytes) funciona. Implementação: a checagem de bytes.
5. `test_factory_raises_when_encryption_key_is_missing`: `monkeypatch.delenv("BROKER_API_KEY_ENCRYPTION_KEY", raising=False)`, mais `get_settings.cache_clear()` e `get_tenant_account_repository.cache_clear()` (padrão de `test_run_audit_e2e.py`), e então `pytest.raises(RuntimeError)`. Implementação: o campo em `Settings` e a factory no container.
6. `test_factory_builds_repository_when_key_is_set`: `setenv` com `Fernet.generate_key().decode()` e `isinstance(..., TenantAccountRepository)`. Limpar os caches no teardown. Esse teste só instancia o engine e não conecta, então não precisa de Docker.

**Fase B: integração do repositório, `tests/integration/persistence/test_tenant_account_repository.py`**

Fixture igual à de `test_pgvector_retriever.py`: `PostgresContainer` com `scope="module"`, engine asyncpg, `await create_all(eng)` de `tables.py` e, a cada teste, `TRUNCATE TABLE tenant_accounts`. Instanciar `TenantAccountRepository(eng, Fernet(Fernet.generate_key()))`. Rodar com `pytest -m integration tests/integration/persistence/test_tenant_account_repository.py -v`.

7. `test_get_by_tenant_returns_none_when_not_found`. Implementação: tabela em `tables.py` e `get_by_tenant`.
8. `test_create_saas_account_round_trips`: cria com api_key `"chave-ção-🔑"` (não-ASCII de propósito), email e senha. O `get_by_tenant` devolve a api_key decifrada igual à original, o email correto, `verify_password(pw, account.password_hash)` verdadeiro e `created_at`/`updated_at` preenchidos. Implementação: `create`, cifragem e hash.
9. `test_broker_api_key_is_encrypted_at_rest`: lê a coluna crua com `select(tenant_accounts_table.c.broker_api_key)` e verifica que o valor é diferente do texto puro, não o contém como substring e que `fernet.decrypt(raw.encode()).decode()` recupera o original.
10. `test_password_is_never_stored_in_plaintext`: a coluna crua `password_hash` é diferente da senha.
11. `test_self_hosted_row_without_login_or_api_key`: `create(tenant, broker_url)` sem os opcionais. Lendo de volta, `broker_api_key`, `login_email` e `password_hash` são todos `None`.
12. `test_duplicate_tenant_is_rejected`: um segundo `create` com o mesmo `Tenant` levanta `IntegrityError`.
13. `test_duplicate_login_email_is_rejected`: dois tenants diferentes com o mesmo email levantam `IntegrityError`.
14. `test_email_without_password_is_rejected`: `create(..., login_email="a@b.c", password=None)` levanta `IntegrityError` (check constraint `login_pair`).
15. `test_empty_broker_url_is_rejected`: `broker_url=""` levanta `IntegrityError`.
16. `test_same_service_different_path_are_isolated`: `Tenant("x", "/a")` e `Tenant("x", "/b")` com api_keys diferentes. Cada `get_by_tenant` devolve só a sua chave. Esse é o teste de isolamento entre tenants.
17. `test_update_broker_changes_url_and_key_and_bumps_updated_at`: depois do update, lê de volta os valores novos, `created_at` fica inalterado e `updated_at >= created_at`. Implementação: `update_broker`.
18. `test_update_broker_on_unknown_tenant_raises_lookup_error`. Implementação: a checagem de `rowcount`.
19. `test_reading_with_a_different_key_raises_invalid_token`: grava com a chave K1 e lê com um repositório usando K2, o que levanta `cryptography.fernet.InvalidToken`. Nunca devolve lixo.

**Fase C: migration, alterando `tests/integration/persistence/test_migrations.py` (testes síncronos, mesmo padrão de `TestKnowledgeChunksSchema`)**

20. Adicionar `"tenant_accounts"` a `EXPECTED_TABLES`. Os testes existentes de upgrade e downgrade passam a cobri-la. Implementação: o arquivo de migration.
21. `TestTenantAccountsSchema::test_duplicate_login_email_is_rejected_by_unique_constraint`: `INSERT` via `text()` depois de `upgrade head`. Garante que a migration não se descolou de `tables.py`, já que a Fase B roda sobre `create_all`.
22. `TestTenantAccountsSchema::test_login_email_without_password_hash_is_rejected`: prova que a check constraint existe na migration.

## 8. Casos de borda cobertos

- Tenant vazio: o `Tenant.__post_init__` existente já levanta `InvalidTenantError`, nada novo aqui.
- Tenant duplicado (12), email duplicado (13, 21).
- `broker_url` ausente: None cai no NOT NULL, e `""` cai na check constraint (15).
- Self-hosted de uma linha só, sem login e sem api_key (11).
- Login pela metade, com email e sem senha (14, 22).
- Unicode na api_key (8) e limite de 72 bytes do bcrypt em UTF-8 (4).
- Chave Fernet errada ou trocada (19). Isolamento entre paths do mesmo service (16).

## 9. Perguntas em aberto (divergências ou ambiguidades com a ADR-0019, não resolvidas aqui)

1. **O tenant é editável no self-hosted?** A ADR §2 diz que a tela de Configuração edita `fiware-service`/`fiware-service-path`. Aqui eles são a PK, e `update_broker` não troca tenant. Como fazer isso: `delete`+`create`, update da PK ou um `id` surrogate? Decidir antes da tela de Configuração.
2. **Maiúsculas/minúsculas no `login_email`.** O UNIQUE diferencia `A@x.com` de `a@x.com`. Normalizar com `.strip().lower()` no `create`? O plano atual não normaliza.
3. **A chave Fernet no self-hosted.** A ADR diz que o self-hosted não tem `api_key`, mas a factory exige a chave sempre. Opções: gerar a chave automaticamente no `docker-compose.selfhosted`/serviço `migrate`, ou tornar a `Fernet` opcional no repositório. Também falta definir o provisionamento no Terraform/Parameter Store (`infra/terraform/modules/lambda_compute/main.tf` e `compute/user_data/*.tftpl` montam as outras variáveis de ambiente). Isso está fora deste escopo.
4. **Nome da coluna.** A ADR chama o campo de `broker_api_key`, e o plano mantém esse nome, mas a coluna guarda um token cifrado. Renomear para `broker_api_key_encrypted` deixaria mais claro. Fica a decisão.
5. **`FIWARE_API_KEY` no `.env.example`.** Existe no `.env.example`, mas não tem campo em `Settings` (é ignorado por `extra="ignore"`). A ADR §2 diz que o self-hosted não usa api_key. Remover essa variável ou ligá-la a algo?
6. **Rotação de chave.** `MultiFernet` ficou de fora. Sem ele, trocar a chave torna ilegíveis as linhas existentes (é o que o teste 19 documenta). Adicionar quando houver política de rotação.

### Arquivos críticos para a implementação
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tables.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/migrations/versions/92150912594b_add_entity_report_measurement_columns.py (head atual e `down_revision` da nova migration)
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/schema_catalog/catalog_sync_status_repository.py (precedente de repositório Core com `AsyncEngine`)
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/container.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/persistence/test_migrations.py