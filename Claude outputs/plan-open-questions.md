# Plano: implementação das 6 decisões em aberto (tenant_accounts, ADR-0019)

Tudo abaixo foi conferido no código espelhado em `/mnt/user-data/uploads/agent_multi_IA_context_broker`. O diretório não é um repositório git.

---

## 0. Premissas: o que o código confirma e o que precisa de correção

| # | Premissa do pedido | Situação no código real |
|---|---|---|
| P1 | O head atual é `edfd0898f739` | **Confirmado.** A cadeia é `2f62abb9e945 → 42889f2ad3cf → 0cfa66a23db8 → d04e459a57d1 → 92150912594b → edfd0898f739`. Nenhuma outra migration aponta para `edfd0898f739`. |
| P2 | Fixture de referência em `tests/integration/persistence/test_pgvector_retriever.py` | **Corrigido.** O caminho real é `tests/integration/rag/test_pgvector_retriever.py`. O padrão usado (container `pgvector/pgvector:pg16` com escopo de módulo, engine `asyncpg` por teste, `create_all` + `TRUNCATE`) é exatamente o que `tests/integration/persistence/test_tenant_account_repository.py` já segue. |
| P3 | "Os serviços `app` e `migrate` precisam da chave" | **Parcialmente falso hoje.** O `migrate` roda `alembic upgrade head && audit knowledge sync` e nenhum dos dois toca em `TenantAccountRepository`/`get_tenant_account_repository`. Mesmo assim, o plano entrega a chave aos dois pelo mesmo entrypoint, e é o `migrate` que a gera, porque ele roda primeiro (`app` tem `depends_on: migrate: service_completed_successfully`). |
| P4 | Self-hosted cifra `broker_api_key` | **Observação.** Pela ADR-0019 §2, a linha self-hosted **não tem** `api_key` (fica NULL). A chave só é necessária porque `get_tenant_account_repository()` se recusa a construir o repositório sem ela, e a futura tela de Configuração usará essa factory. O mecanismo continua necessário. |
| P5 | `FIWARE_API_KEY` sem uso | **Confirmado.** Não há campo em `Settings`, e `extra="ignore"` descarta a variável. Ela também aparece no `.env` local do usuário (fora do git, pelo `.gitignore`) e em `docs/fases/fase-04-integracao-fiware-ngsi.md:32`. Ver a seção de ambiguidades. |
| P6 | Bug latente no estado atual | Com `BROKER_API_KEY_ENCRYPTION_KEY=` vazio (como no `.env.example`), o pydantic gera `SecretStr("")`, e não `None`. `Fernet("")` levanta `ValueError`, e não o `RuntimeError` pretendido. O desenho com lista (decisão 6) corrige isso sem custo extra, porque string vazia vira `[]`. |
| P7 | **Bloqueador pré-existente do self-hosted** (fora das 6 decisões) | `selfhosted/Dockerfile` só copia `requirements.txt`, `pyproject.toml` e `src/`. **Não copia `alembic.ini`, `migrations/` nem `knowledge/`.** Com isso, `alembic upgrade head` falha por falta de config e `CorpusLoader.KNOWLEDGE_DIR` (`parents[4]/"knowledge"`, que dá `/app/knowledge`) não existe. O serviço `migrate` já está quebrado hoje e a verificação manual da decisão 3 vai esbarrar nisso. Não corrijo aqui; ver a seção de ambiguidades. |
| P8 | Arquivos duplicados na raiz | `Dockerfile.selfhosted` e `docker-compose.selfhosted.yml` na raiz são cópias antigas (`context: .`, sem frontend). O README só referencia `selfhosted/`. Esses arquivos **não** recebem o mecanismo de chave. Ver a seção de ambiguidades. |
| P9 | Tipo do campo de lista no `Settings` | O pydantic-settings 2.14 (instalado) tenta decodificar **como JSON** os campos `list[...]` vindos do ambiente, então `k1,k2` quebraria. O padrão já usado no projeto (`cors_allowed_origins: str` + propriedade `_list`) evita isso e será reaproveitado. |
| P10 | O dataclass `TenantAccount.broker_api_key` e os parâmetros `broker_api_key` dos métodos | **Não mudam de nome.** Eles carregam o valor **em texto puro** (entrada e saída do repositório). Só a **coluna** guarda o valor cifrado e passa a se chamar `broker_api_key_encrypted`. |
| P11 | Comportamento do `MultiFernet` | Verificado com cryptography 46.0.7: `MultiFernet([])` levanta `ValueError`, `Fernet("")` e chaves malformadas levantam `ValueError`, `encrypt` usa a primeira chave e `decrypt` tenta todas. |

---

## 1. Arquivos alterados e novos

**Alterados**
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tables.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/settings.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/container.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/.env.example`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/selfhosted/Dockerfile`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/selfhosted/docker-compose.yml`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/docs/adr/adr-0019.md`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/README.md` (um parágrafo na seção self-hosted)
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/persistence/test_tenant_account_repository.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/persistence/test_migrations.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/config/test_tenant_account_repository_factory.py`

**Novos**
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/migrations/versions/5c1f3a8e2b7d_rename_broker_api_key_to_encrypted.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/selfhosted/fernet-keys.sh`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/config/test_settings_encryption_keys.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/config/test_selfhosted_fernet_keys_script.py`

`tests/` não tem nenhum `__init__.py`, então os basenames dos testes precisam ser únicos. Os dois nomes novos foram conferidos e não colidem com nenhum existente. O revision id `5c1f3a8e2b7d` também foi conferido e não colide em `migrations/`.

---

## 2. Esquema de cada mudança

### Decisão 5: remover `FIWARE_API_KEY` do `.env.example`
Apagar a linha 5 (`FIWARE_API_KEY=`). A mudança não precisa de teste.

### Decisão 4: renomear a coluna `broker_api_key` para `broker_api_key_encrypted`

**Migration nova**, escrita à mão no mesmo formato de `edfd0898f739`. A docstring é o cabeçalho padrão do Alembic, igual às migrations existentes.

```python
"""rename tenant_accounts.broker_api_key to broker_api_key_encrypted (ADR-0019)

Revision ID: 5c1f3a8e2b7d
Revises: edfd0898f739
Create Date: 2026-09-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "5c1f3a8e2b7d"
down_revision: Union[str, None] = "edfd0898f739"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("tenant_accounts", "broker_api_key", new_column_name="broker_api_key_encrypted")


def downgrade() -> None:
    op.alter_column("tenant_accounts", "broker_api_key_encrypted", new_column_name="broker_api_key")
```
No Postgres isso vira `ALTER TABLE ... RENAME COLUMN`. Os dados são preservados, mas nenhuma linha real existe fora dos testes (a decisão 6 já confirma isso).

**Todos os pontos que usam o nome antigo da coluna** (levantados por grep completo):
- `tables.py:161`: `Column("broker_api_key", ...)` passa a `Column("broker_api_key_encrypted", String, nullable=True)`.
- `tenant_account_repository.py:63`: `broker_api_key=encrypted_api_key` no insert do `create`.
- `tenant_account_repository.py:85-86`: `row["broker_api_key"]` (2 ocorrências) no `get_by_tenant`.
- `tenant_account_repository.py:118`: `broker_api_key=encrypted_api_key` no `.values()` do `update_broker`.
- `tests/integration/persistence/test_tenant_account_repository.py:90`: `tenant_accounts_table.c.broker_api_key`.
- `docs/adr/adr-0019.md:37`: o texto `broker_api_key` (criptografada em repouso) passa a `broker_api_key_encrypted`. As linhas 42, 60 e 163 falam do conceito (a api key em texto puro) e ficam como estão.
- `.env.example`, no comentário do bloco final (ver decisão 6).

A migration `edfd0898f739` **não** é editada, porque fica como histórico.

### Decisão 6: `MultiFernet` com lista de chaves

**`settings.py`**: troca o campo singular por uma lista, no mesmo padrão de `cors_allowed_origins`.
```python
broker_api_key_encryption_keys: SecretStr | None = None

@property
def broker_api_key_encryption_keys_list(self) -> list[str]:
    if self.broker_api_key_encryption_keys is None:
        return []
    return [
        key.strip()
        for key in self.broker_api_key_encryption_keys.get_secret_value().split(",")
        if key.strip()
    ]
```
`SecretStr` continua em uso para a chave não vazar em `repr(settings)` nem em logs.

**`container.py`**:
```python
from cryptography.fernet import Fernet, MultiFernet
...
@lru_cache
def get_tenant_account_repository() -> TenantAccountRepository:
    keys = get_settings().broker_api_key_encryption_keys_list
    if not keys:
        raise RuntimeError("BROKER_API_KEY_ENCRYPTION_KEYS nao configurada")
    return TenantAccountRepository(get_engine(), MultiFernet([Fernet(key) for key in keys]))
```
Uma chave malformada deixa o `ValueError` do `Fernet(key)` propagar. Isso é fail-fast de propósito: a factory quebra na construção, e não na primeira leitura.

**`tenant_account_repository.py`**: o construtor passa a receber um `MultiFernet`. O nome do parâmetro e do atributo (`fernet`/`_fernet`) é mantido para o diff ficar mínimo, porque a API `encrypt`/`decrypt` é a mesma.
```python
from cryptography.fernet import MultiFernet

def __init__(self, engine: AsyncEngine, fernet: MultiFernet) -> None:
```
Hoje a expressão de cifragem aparece duplicada em `create` e `update_broker`, e a decisão 1 criaria uma terceira cópia. Por isso o plano extrai **um** helper privado:
```python
def _encrypt(self, value: str | None) -> str | None:
    return self._fernet.encrypt(value.encode("utf-8")).decode("ascii") if value is not None else None
```
Os três métodos (`create`, `update_broker` e `replace_tenant`) passam a usar `self._encrypt(broker_api_key)`.

**`.env.example`**: o bloco final fica assim (comentário de configuração, no estilo que o arquivo já usa):
```
# ADR-0019 — chaves Fernet (lista separada por vírgula) usadas para cifrar
# tenant_accounts.broker_api_key_encrypted em repouso. A primeira da lista
# cifra; todas decifram. Rotação: coloque a nova na frente, re-cifre as
# linhas, depois remova a antiga. Gerar cada chave com Fernet.generate_key().
BROKER_API_KEY_ENCRYPTION_KEYS=
```

### Decisão 2: normalizar `login_email`
Só no `create`, porque não existe nenhum outro método que busque por email:
```python
normalized_email = login_email.strip().lower() if login_email is not None else None
```
Esse valor substitui `login_email` no `.values()` do insert. O `replace_tenant` reaproveita o email já gravado, que já estará normalizado.

### Decisão 1: substituir o tenant atomicamente (`replace_tenant`)

```python
async def replace_tenant(
    self,
    old_tenant: Tenant,
    new_tenant: Tenant,
    broker_url: str,
    broker_api_key: str | None,
) -> None:
    encrypted_api_key = self._encrypt(broker_api_key)
    async with self._engine.begin() as conn:
        deleted = (
            await conn.execute(
                tenant_accounts_table.delete()
                .where(
                    tenant_accounts_table.c.fiware_service == old_tenant.fiware_service,
                    tenant_accounts_table.c.fiware_service_path == old_tenant.fiware_service_path,
                )
                .returning(
                    tenant_accounts_table.c.login_email,
                    tenant_accounts_table.c.password_hash,
                )
            )
        ).first()
        if deleted is None:
            raise LookupError(
                f"tenant_account nao encontrado para {old_tenant.fiware_service}"
                f"/{old_tenant.fiware_service_path}"
            )
        await conn.execute(
            tenant_accounts_table.insert().values(
                fiware_service=new_tenant.fiware_service,
                fiware_service_path=new_tenant.fiware_service_path,
                broker_url=broker_url,
                broker_api_key_encrypted=encrypted_api_key,
                login_email=deleted.login_email,
                password_hash=deleted.password_hash,
            )
        )
```
Como a atomicidade é garantida:
- `engine.begin()` abre **uma** transação explícita, faz commit ao sair do bloco e rollback em qualquer exceção. É o mesmo mecanismo que `create` e `update_broker` já usam.
- `DELETE ... RETURNING` busca e apaga a linha num único comando, sem janela entre um `SELECT` e o `DELETE`.
- Qualquer falha no `INSERT` desfaz o `DELETE`: colisão de PK com outro tenant existente, violação de `ck_tenant_accounts_broker_url_not_empty` ou queda de conexão.
- A cifragem roda **antes** de abrir a transação, então um erro de chave nunca começa a transação.
- O `LookupError` é levantado dentro do bloco, e o rollback não tem efeito porque nada mudou.

Escolha de desenho (listada como ambiguidade): `login_email`/`password_hash` são **copiados** da linha antiga. Assim a troca não apaga o login de uma conta SaaS sem aviso. Em self-hosted esses campos são NULL, então o efeito é nulo. `created_at`/`updated_at` recebem o `now()` do `server_default` da linha nova.

### Decisão 3: chave Fernet gerada automaticamente no self-hosted

**Mecanismo:** um script POSIX de entrypoint, copiado para a imagem, que:
1. gera a chave se o arquivo no volume nomeado não existir ou estiver vazio (com `umask 077`, gravação em `.tmp` e depois `mv` atômico);
2. lê o arquivo e exporta `BROKER_API_KEY_ENCRYPTION_KEYS`;
3. faz `exec "$@"`, para o uvicorn virar PID 1 e receber os sinais.

**`selfhosted/fernet-keys.sh`** (código final sem comentários):
```sh
#!/bin/sh
set -eu
KEY_FILE="${BROKER_API_KEY_ENCRYPTION_KEYS_FILE:-/var/lib/auditor-secrets/broker_api_key_encryption_keys}"
if [ ! -s "$KEY_FILE" ]; then
  umask 077
  python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' > "$KEY_FILE.tmp"
  mv "$KEY_FILE.tmp" "$KEY_FILE"
fi
BROKER_API_KEY_ENCRYPTION_KEYS="$(cat "$KEY_FILE")"
export BROKER_API_KEY_ENCRYPTION_KEYS
exec "$@"
```
A variável `BROKER_API_KEY_ENCRYPTION_KEYS_FILE` existe só para o teste unitário apontar para um `tmp_path`. Nada no compose a define.

**`selfhosted/Dockerfile`**: acrescentar depois do `RUN pip install` (para não invalidar o cache das dependências) e antes do `EXPOSE`/`CMD`:
```dockerfile
COPY selfhosted/fernet-keys.sh /usr/local/bin/fernet-keys.sh
ENTRYPOINT ["sh", "/usr/local/bin/fernet-keys.sh"]
```
O `CMD` do uvicorn continua igual e vira `"$@"` do script. Chamar o script via `sh` dispensa `chmod` e `COPY --chmod`. O build context `..` (raiz do repo) já permite o caminho `selfhosted/fernet-keys.sh`.

**`selfhosted/docker-compose.yml`**:
- Serviço `migrate`: **remover** a linha `entrypoint: [...]`, trocar por `command: ["sh", "-c", "alembic upgrade head && audit knowledge sync"]` e acrescentar:
  ```yaml
      volumes:
        - auditor-secrets:/var/lib/auditor-secrets
  ```
- Serviço `app`: acrescentar a montagem **somente leitura**, porque quem gera a chave é o `migrate`, que sempre roda antes:
  ```yaml
      volumes:
        - auditor-secrets:/var/lib/auditor-secrets:ro
  ```
- Bloco `volumes:` no fim do arquivo: acrescentar `auditor-secrets:`.

Propriedades de segurança garantidas:
- A chave nunca aparece em camada de imagem, no compose, no git ou em `docker inspect`/`docker compose config`, porque é exportada pelo processo em tempo de execução e não pela configuração do container.
- O arquivo fica com permissão 0600.
- O `app` não consegue sobrescrever a chave.
- Um crash no meio da geração nunca deixa um arquivo pela metade (o `.tmp` não é renomeado, e `-s` regenera se o arquivo existir vazio).
- Rotação no self-hosted: editar o arquivo no volume para `nova,antiga`. O script repassa o conteúdo sem mudar nada.
- Futuros `docker compose run --rm app audit ...` passam pelo mesmo entrypoint e recebem a chave.

**README (seção self-hosted)**, um parágrafo: a chave de cifragem é gerada sozinha no volume `auditor-secrets`, que precisa entrar no backup junto com `auditor-postgres-data`. Perder só o primeiro torna ilegíveis as `broker_api_key` cifradas. `docker compose down -v` apaga os dois.

**ADR-0019**: acrescentar três itens curtos.
- Na §1: a coluna chama-se `broker_api_key_encrypted`, a cifragem usa `MultiFernet` com `BROKER_API_KEY_ENCRYPTION_KEYS` (a primeira cifra e todas decifram) e a rotação segue o procedimento do `.env.example`.
- Na §1: `login_email` é normalizado com `strip().lower()`.
- Na §2: a chave é gerada automaticamente no volume `auditor-secrets` por `selfhosted/fernet-keys.sh`, e a troca de tenant na tela de Configuração usa `replace_tenant` (delete + insert atômicos), nunca UPDATE de PK.

---

## 3. Sequência TDD

Ordem: 5 → 4 → 6 → 2 → 1 → 3. A 4 vem antes da 6 porque as duas mexem no mesmo arquivo de integração e na mesma fixture.

Comandos:
- **[U]** unitário, roda sem Docker: `pytest tests/unit -q`
- **[I]** integração, precisa de Docker (testcontainers): `pytest -m integration tests/integration/persistence -v`

**Passo 1 (decisão 5), sem teste.** Remover `FIWARE_API_KEY=` do `.env.example`.

**Passo 2 [I] (decisão 4), vermelho.** Em `test_migrations.py`, classe `TestTenantAccountsSchema`, acrescentar `test_broker_api_key_column_is_renamed_to_encrypted`. O teste é síncrono, como os vizinhos, e segue o mesmo padrão: `_alembic_config`, `command.upgrade(cfg, "head")`, inspeção via `asyncio.run` + `run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("tenant_accounts")})`. Verificações:
- depois do `head`, `broker_api_key_encrypted` está entre as colunas e `broker_api_key` não;
- depois de `command.downgrade(cfg, "edfd0898f739")`, vale o inverso;
- no fim, `command.downgrade(cfg, "base")`.

Os testes de upgrade/downgrade já existentes cobrem o encadeamento `base ↔ head` com a migration nova.

**Passo 3 [I], vermelho.** Em `test_tenant_account_repository.py::test_broker_api_key_is_encrypted_at_rest`, trocar `tenant_accounts_table.c.broker_api_key` por `.c.broker_api_key_encrypted`. O teste falha com `AttributeError`.

**Passo 4, verde.** Criar a migration `5c1f3a8e2b7d`, trocar o nome da coluna em `tables.py` e atualizar as 3 referências no repositório. Os passos 2 e 3 ficam verdes, e o restante da suíte [I] de `tenant_account` continua verde.

**Passo 5 [U] (decisão 6), vermelho.** Criar `test_settings_encryption_keys.py` no estilo de `test_settings_cors.py`, sempre com `Settings(_env_file=None, ...)`:
- `broker_api_key_encryption_keys=" k2 , k1 ,"` dá a lista `["k2", "k1"]` (ordem preservada, espaços e itens vazios descartados);
- sem o campo, a lista é `[]`;
- `broker_api_key_encryption_keys=""` dá `[]`;
- `"k2" not in repr(Settings(_env_file=None, broker_api_key_encryption_keys="k2"))`, o que prova que o `SecretStr` não vaza.

**Passo 6, verde.** Trocar o campo e adicionar a propriedade em `settings.py`.

**Passo 7 [U], vermelho.** Em `test_tenant_account_repository_factory.py`:
- renomear para `BROKER_API_KEY_ENCRYPTION_KEYS` nos testes existentes;
- `test_factory_raises_when_keys_are_blank`: `setenv(..., " , ")` levanta `RuntimeError`;
- `test_factory_rejects_a_malformed_key`: `setenv(..., "nao-e-uma-chave")` levanta `ValueError`;
- `test_factory_encrypts_with_first_key_and_decrypts_with_all`: gerar `k1` e `k2` e fazer `setenv(..., f"{k2},{k1}")`. Depois:
  - `repo._fernet.decrypt(Fernet(k1).encrypt(b"x")) == b"x"`;
  - `token = repo._fernet.encrypt(b"y")`;
  - `Fernet(k2).decrypt(token) == b"y"`;
  - `pytest.raises(InvalidToken): Fernet(k1).decrypt(token)`.

  É o único teste sem Docker que pega uma lista invertida na factory. Ele acessa `_fernet` de propósito: é a forma mais barata de verificar a ordem num caminho de segurança.

**Passo 8, verde.** Mudar `container.py`.

**Passo 9 [I], vermelho.** Em `test_tenant_account_repository.py`:
- a fixture `fernet` passa a devolver `MultiFernet([Fernet(Fernet.generate_key())])`;
- `TestEncryptionKeyMismatch` é renomeada para `TestKeyRotation` e passa a usar `MultiFernet` nos dois repositórios;
- `test_reading_with_a_different_key_raises_invalid_token` é mantido, com `[k1]` contra `[k2]`;
- **novo** `test_rotated_repository_reads_rows_written_with_the_old_key`: o writer usa `[k1]` e cria `TENANT_A` com `"chave-secreta"`; o reader usa `[k2, k1]` e `get_by_tenant` devolve `"chave-secreta"`;
- **novo** `test_rotated_repository_encrypts_new_writes_with_the_new_key`: um repositório `[k2, k1]` cria `TENANT_B`; o valor bruto de `broker_api_key_encrypted` decifra com `Fernet(k2)`, e `Fernet(k1).decrypt(raw)` levanta `InvalidToken`.

**Passo 10, verde.** Trocar o type hint do construtor para `MultiFernet` e extrair o `_encrypt`. O `create`/`update_broker` fica sem mudança de comportamento, e toda a suíte [I] continua verde.

**Passo 11 [I] (decisão 2), vermelho.** Em `TestCreate`:
- `test_login_email_is_normalized_on_create`: `"  Tenant@Example.COM "` é lido de volta como `"tenant@example.com"`;
- `test_duplicate_login_email_differing_only_by_case_is_rejected`: criar `"dup@example.com"` e depois `" DUP@Example.com"` num outro tenant levanta `IntegrityError`.

**Passo 12, verde.** Normalizar o email no `create`.

**Passo 13 [I] (decisão 1), vermelho.** Criar a classe `TestReplaceTenant` com um helper local `_count(engine)` que roda `select(func.count()).select_from(tenant_accounts_table)`. Casos:
1. `test_replace_moves_account_to_new_tenant`: `create(A, url1, "chave-1", "a@x.com", "senha")` seguido de `replace_tenant(A, C, url2, "chave-2")`. Resultado: `get_by_tenant(A) is None`, `C` tem `url2` e `"chave-2"`, o email `"a@x.com"` é preservado, `verify_password("senha", ...)` continua válido e `_count == 1`.
2. `test_replace_unknown_tenant_raises_lookup_error_and_creates_nothing`: levanta `LookupError`, `_count == 0` e `get_by_tenant(C) is None`.
3. `test_replace_into_existing_tenant_rolls_back_leaving_both_rows_intact` (**atomicidade: falha real no meio**): criar `A` (url1, "chave-a") e `B` (url2, "chave-b"). `replace_tenant(A, B, url3, "chave-x")` levanta `IntegrityError`, porque o DELETE de A já rodou e o INSERT colide com a PK de B. Depois disso: A continua com url1 e "chave-a", B continua com url2 e "chave-b", e `_count == 2`. Ou seja, o banco não fica com zero linhas para A nem com duplicata.
4. `test_replace_with_invalid_broker_url_rolls_back_keeping_old_row` (**atomicidade: violação de CHECK depois do DELETE**): criar `A`. `replace_tenant(A, C, "", None)` levanta `IntegrityError`. Depois disso: A está intacto, `get_by_tenant(C) is None` e `_count == 1`, ou seja, o banco nunca fica com zero linhas.
5. `test_replace_with_same_tenant_behaves_as_update`: `replace_tenant(A, A, url2, "chave-2")` deixa `_count == 1` e A com os valores novos.

**Passo 14, verde.** Implementar `replace_tenant`.

**Passo 15 [U] (decisão 3), vermelho.** Criar `test_selfhosted_fernet_keys_script.py`, com `@pytest.mark.skipif(sys.platform == "win32", ...)` no módulo.
- Caminho do script: `SCRIPT = Path(__file__).resolve().parents[4] / "selfhosted" / "fernet-keys.sh"`.
- Helper `_run(key_file)`:
  - executa `subprocess.run(["sh", str(SCRIPT), sys.executable, "-c", "import os; print(os.environ['BROKER_API_KEY_ENCRYPTION_KEYS'])"], env=..., capture_output=True, text=True, check=True)`;
  - o `env` é `os.environ` sem `BROKER_API_KEY_ENCRYPTION_KEYS`, mais `BROKER_API_KEY_ENCRYPTION_KEYS_FILE=str(key_file)`, mais o `PATH` com `os.path.dirname(sys.executable)` na frente, para o `python3` do script ser o do venv, que tem `cryptography`.

  Casos:
  - `test_generates_owner_only_valid_key_when_missing`: o arquivo passa a existir, `stat.S_IMODE(...) == 0o600`, `Fernet(conteudo)` não levanta erro e o stdout do filho é igual ao conteúdo.
  - `test_reuses_existing_key_across_runs`: duas execuções devolvem o mesmo valor.
  - `test_passes_rotation_list_through_unchanged`: com o arquivo pré-escrito `"k2,k1\n"`, o stdout é `"k2,k1"`.
  - `test_regenerates_when_file_is_empty`: com o arquivo vazio, sai uma chave Fernet válida.
  - Também não pode sobrar nenhum `*.tmp` no diretório.

**Passo 16, verde.** Criar `selfhosted/fernet-keys.sh`.

**Passo 17, sem teste automatizado.** Editar `selfhosted/Dockerfile` e `selfhosted/docker-compose.yml`. Validar a sintaxe com `docker compose -f selfhosted/docker-compose.yml config`. O `docker compose up` completo **depende de resolver P7** (ver a seção de ambiguidades).

**Passo 18, só documentação.** Atualizar o bloco final do `.env.example`, o parágrafo do README e os itens da ADR-0019.

**Passo 19, suíte completa.** Rodar `pytest tests/unit -q` e depois `pytest -m integration -v`.

---

## 4. Casos de borda cobertos

- A lista de chaves tem ordem significativa: a primeira cifra, e isso é verificado no teste unitário da factory e no de integração.
- Lista vazia ou só espaços e vírgulas gera `RuntimeError` claro. Isso corrige o P6, em que a string vazia virava `ValueError`.
- Uma chave malformada na lista gera `ValueError` na construção, e não na primeira leitura.
- Um token de chave desconhecida gera `InvalidToken`, e o teste existente foi mantido.
- A chave não vaza no `repr(Settings)`.
- Email com espaços ou maiúsculas é normalizado, e duplicatas que diferem só na caixa são barradas pelo `uq_tenant_accounts_login_email` existente.
- `replace_tenant`:
  - tenant de origem inexistente;
  - destino já ocupado (rollback);
  - violação de CHECK depois do DELETE (rollback);
  - origem igual ao destino;
  - preservação do login.
- Script de chave:
  - arquivo ausente, vazio ou com lista de rotação;
  - permissão 0600;
  - sem `.tmp` sobrando;
  - reuso entre reinicializações;
  - `app` com montagem somente leitura;
  - `exec` para repasse de sinais.
- Migration: upgrade e downgrade específicos até `edfd0898f739`, mais o ciclo `base ↔ head` já coberto.

---

## 5. Ambiguidades residuais, não resolvidas porque nenhuma das 6 decisões as cobre

1. **P7, que bloqueia a validação real do self-hosted.** `selfhosted/Dockerfile` não copia `alembic.ini`, `migrations/` nem `knowledge/`, então o `migrate` falha hoje. A correção provável é de 3 linhas (`COPY alembic.ini ./`, `COPY migrations ./migrations`, `COPY knowledge ./knowledge`), mas ela está fora de escopo e precisa de aprovação. **[Resolvido pelo orquestrador: incluído no lote de código desta rodada, por ser um bug de baixo risco e correção trivial — ver nota abaixo do plano.]**
2. **P8.** O que fazer com `Dockerfile.selfhosted` e `docker-compose.selfhosted.yml` na raiz. **[Verificado pelo orquestrador diretamente no dispositivo real: esses arquivos já não existem lá — a limpeza já tinha sido feita numa rodada anterior. O plano viu o mirror local, que estava desatualizado. Sem ação necessária.]**
3. **Re-cifragem na rotação.** O procedimento pressupõe "re-cifrar todas as linhas", mas não existe ferramenta para isso. Um esboço de ~10 linhas: um método `rotate_encryption()` que roda `MultiFernet.rotate(token)` em cada linha com `broker_api_key_encrypted` não nulo, numa transação, exposto por um comando administrativo. Precisa de decisão.
4. **`replace_tenant` copia `login_email`/`password_hash` da linha antiga.** Escolhi a opção que não destrói dados, mas a regra de negócio para contas SaaS não foi definida. Alternativa: recusar `replace_tenant` em linhas que têm login.
5. **Histórico de auditorias.** `audit_runs` guarda `tenant_fiware_service`/`_path` de forma desnormalizada, sem FK. Depois do `replace_tenant`, as auditorias antigas continuam no tenant antigo e não aparecem no novo. Isso é aceitável?
6. **Email vazio depois da normalização.** Um email só com espaços vira `""` e passa pelo CHECK (não é NULL). Rejeitar com `ValueError` no `create` custaria uma linha, mas não foi decidido.
7. **Perda isolada do volume `auditor-secrets` com o banco preservado.** O `migrate` gera uma chave nova em silêncio e as linhas cifradas antigas ficam ilegíveis (`InvalidToken`). Hoje o impacto é nulo, porque o self-hosted não grava api key (P4). Uma guarda do tipo "recusar gerar chave se houver linhas cifradas" não foi decidida. Por enquanto a mitigação é o parágrafo de backup no README.
8. **`FIWARE_API_KEY` em outros lugares.** A variável continua no `.env` local do usuário (fora do git, basta ele apagar) e em `docs/fases/fase-04-integracao-fiware-ngsi.md:32`, que é um documento histórico de fase. Editar esse documento ou não?
9. **Isolamento do teste da factory.** O `Settings()` lê o `.env` do diretório atual. Se o `.env` de um desenvolvedor tiver `BROKER_API_KEY_ENCRYPTION_KEYS`, o teste "raises when missing" falha. O problema já existia com a variável singular. Um `monkeypatch.chdir(tmp_path)` resolve, mas não mexi porque não estava pedido.

---

### Critical Files for Implementation
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/container.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/settings.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/selfhosted/docker-compose.yml
- /mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/persistence/test_tenant_account_repository.py
