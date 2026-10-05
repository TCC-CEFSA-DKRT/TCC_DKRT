# Plano: rotação de chave, `replace_tenant` recusando contas com login, auditorias antigas, fase-04

Resumo: das quatro decisões, só a 1 (rotação) e a 2 (`replace_tenant`) mexem em código. A 3 e a 4 são só texto na ADR-0019 e no `fase-04`. Conferi tudo no repositório espelhado. Não existe erro de domínio que sirva para a recusa, então o plano usa `ValueError`.

## 0. Premissas conferidas no código

| # | Premissa | Resultado |
|---|---|---|
| P1 | `replace_tenant` faz `DELETE ... RETURNING (login_email, password_hash)` e depois `INSERT` copiando os dois, tudo dentro de `async with self._engine.begin()` | **Confirmada** (`tenant_account_repository.py`, fim do arquivo) |
| P2 | Uma exceção dentro de `engine.begin()` desfaz o `DELETE` | **Confirmada**. `AsyncEngine.begin()` faz rollback quando uma exceção atravessa o bloco. Dois testes que já passam provam isso na prática: `test_replace_into_existing_tenant_rolls_back_leaving_both_rows_intact` e `test_replace_with_invalid_broker_url_rolls_back_keeping_old_row` (o `DELETE` é desfeito quando o `INSERT` dá `IntegrityError`) |
| P3 | `MultiFernet.rotate` | **Confirmada** na versão instalada, cryptography 46.0.7 (o `pyproject` pede `>=42.0.0`). Assinatura: `rotate(self, msg: bytes \| str) -> bytes`. Tenta decifrar com cada chave na ordem, cifra de novo com `self._fernets[0]` e **mantém o timestamp original**. Se nenhuma chave decifrar, levanta `InvalidToken` |
| P4 | Erro de domínio específico | **Não existe nenhum adequado**. `domain/errors.py` avisa que `DomainError` é para violações "sob `auditor.domain`". O próprio repositório (infraestrutura) já usa exceção da stdlib (`LookupError`). Usar **`ValueError`** mantém esse padrão |
| P5 | Padrão do CLI | **Typer**. `app = typer.Typer(...)`, subgrupos via `x_app = typer.Typer(help=...)` + `app.add_typer(x_app, name="x")` + `@x_app.command("sync")`. O corpo segue sempre o mesmo formato: `async def _f()` que pega a factory do container **dentro** da função, depois `asyncio.run` dentro de `try/except Exception` com `typer.echo(..., err=True)` e `raise typer.Exit(code=1)`. Entry point: `audit = "auditor.interfaces.cli.main:app"` |
| P6 | Grupo `tenant` no CLI | **Ainda não existe**. A ADR-0019 cita `audit tenant register` como planejado, mas não foi implementado. Este plano cria o grupo `tenant_app`, e o `register` entra nele depois |
| P7 | Testes do CLI | `tests/unit/interfaces/cli/test_cli.py`. Usam `CliRunner` e trocam as factories por `monkeypatch.setattr(cli_main, "get_...", lambda: Fake(...))`. Rodam **sem Docker** |
| P8 | `audit_runs` | **Confirmada**. Guarda `tenant_fiware_service`/`tenant_fiware_service_path` como `String`, sem FK para `tenant_accounts`. `replace_tenant` só mexe em `tenant_accounts_table` |
| P9 | `FIWARE_API_KEY` | Aparece em um único lugar do repositório: `docs/fases/fase-04-integracao-fiware-ngsi.md:32`, na linha da tabela `\| Variáveis de ambiente \| \`FIWARE_BROKER_URL\`, \`FIWARE_API_KEY\` \|`. O `.env.example` real tem `FIWARE_BROKER_URL`, `FIWARE_SERVICE` e `FIWARE_SERVICE_PATH` |
| P10 | `str(InvalidToken())` | Dá `''`. O `except Exception` genérico do CLI imprimiria "Erro ...: " sem nenhuma explicação, por isso o plano trata esse caso à parte (ver 1.3) |

## Arquivos

| Arquivo | Mudança |
|---|---|
| `src/auditor/infrastructure/persistence/tenant_account_repository.py` | novo método `rotate_encryption()`; `replace_tenant` passa a recusar linha com login |
| `src/auditor/interfaces/cli/main.py` | novo grupo `tenant` com o comando `rotate-keys` |
| `tests/integration/persistence/test_tenant_account_repository.py` | 2 testes de rotação; o teste de replace atual é reescrito e ganha um teste de recusa |
| `tests/unit/interfaces/cli/test_cli.py` | `TestTenantRotateKeysCommand` com 3 testes |
| `docs/adr/adr-0019.md` | três trechos de texto |
| `docs/fases/fase-04-integracao-fiware-ngsi.md` | correção só na linha 32 |
| `.env.example` | uma palavra no comentário da rotação (opcional, ver 1.4) |

Nenhum arquivo novo, nenhuma migration nova, `container.py` e `settings.py` ficam como estão: `get_tenant_account_repository()` já monta o `MultiFernet` a partir da lista.

---

## 1. Rotação de chave

### 1.1 Repositório: `rotate_encryption()`

Acrescentar logo depois de `replace_tenant`. Os imports já existem (`select`, `tenant_accounts_table`).

```python
    async def rotate_encryption(self) -> int:
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        tenant_accounts_table.c.fiware_service,
                        tenant_accounts_table.c.fiware_service_path,
                        tenant_accounts_table.c.broker_api_key_encrypted,
                    )
                    .where(tenant_accounts_table.c.broker_api_key_encrypted.is_not(None))
                    .order_by(
                        tenant_accounts_table.c.fiware_service,
                        tenant_accounts_table.c.fiware_service_path,
                    )
                    .with_for_update()
                )
            ).all()
            for row in rows:
                await conn.execute(
                    tenant_accounts_table.update()
                    .where(
                        tenant_accounts_table.c.fiware_service == row.fiware_service,
                        tenant_accounts_table.c.fiware_service_path == row.fiware_service_path,
                    )
                    .values(
                        broker_api_key_encrypted=self._fernet.rotate(
                            row.broker_api_key_encrypted.encode("ascii")
                        ).decode("ascii")
                    )
                )
        return len(rows)
```

Por que cada parte está aí (isto não vai para o código):
- **Uma transação só**: se uma linha não decifrar (`InvalidToken`), tudo volta atrás e nenhuma linha fica com chave nova e outra com a antiga. É o mesmo mecanismo de P2.
- **`with_for_update()`**: sem o lock, um `update_broker` rodando ao mesmo tempo poderia gravar uma chave nova e a rotação a sobrescreveria com a versão re-cifrada da chave **antiga**, perdendo dado. Com o lock, o `update_broker` espera o commit e grava por cima.
- **`order_by` pela PK**: os locks são sempre pegos na mesma ordem, o que evita deadlock se duas rotações rodarem juntas. Também torna determinístico o teste de atomicidade (1.5, teste B).
- **`updated_at` não é alterado**: o valor da api key não muda, só o material de cifragem. Veja a ambiguidade A1.
- `rotate()` aceita `bytes | str`. Mantive `.encode("ascii")` para ficar igual a `get_by_tenant`.
- Um `UPDATE` por linha é suficiente para o volume do TCC. Se o volume crescer, dá para trocar por executemany com `bindparam`.

### 1.2 Como rotacionar na prática (vai também para a ADR)

1. Gerar `k2`. Configurar `BROKER_API_KEY_ENCRYPTION_KEYS=k2,k1` e reiniciar API e worker (a partir daí, escrita nova já sai com `k2` e leitura aceita as duas).
2. Rodar `audit tenant rotate-keys` (re-cifra tudo com `k2`).
3. Configurar `BROKER_API_KEY_ENCRYPTION_KEYS=k2` e reiniciar.

### 1.3 CLI: `audit tenant rotate-keys`

Em `main.py`:
- import: `from cryptography.fernet import InvalidToken`
- acrescentar `get_tenant_account_repository` no bloco `from auditor.infrastructure.config.container import (...)`, em ordem alfabética, depois de `get_sync_knowledge_base_use_case`
- bloco novo depois de `knowledge_sync`, antes do `if __name__ == "__main__":`

```python
tenant_app = typer.Typer(help="Comandos administrativos das contas de tenant (ADR-0019).")
app.add_typer(tenant_app, name="tenant")


@tenant_app.command("rotate-keys")
def tenant_rotate_keys() -> None:
    """Re-cifra toda tenant_accounts.broker_api_key_encrypted com a primeira
    chave de BROKER_API_KEY_ENCRYPTION_KEYS (ADR-0019)."""

    async def _rotate() -> int:
        return await get_tenant_account_repository().rotate_encryption()

    try:
        count = asyncio.run(_rotate())
    except InvalidToken:
        typer.echo(
            "Erro ao rotacionar chaves: alguma linha nao decifra com nenhuma chave de "
            "BROKER_API_KEY_ENCRYPTION_KEYS; nada foi alterado.",
            err=True,
        )
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Erro ao rotacionar chaves: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Chaves rotacionadas: {count} linhas re-cifradas com a chave atual.")
```

- A docstring do comando é o texto de `--help` no Typer (o `catalog_sync` e o `knowledge_sync` fazem o mesmo). Pela regra de não ter comentários, ela conta como texto de ajuda e fica.
- `get_tenant_account_repository()` é chamada **dentro** de `_rotate`, como nos outros comandos. Assim o `RuntimeError("BROKER_API_KEY_ENCRYPTION_KEYS nao configurada")` e o `ValueError` de chave malformada caem no `except Exception`, sem traceback cru na tela.
- O `except InvalidToken` vem antes do genérico por causa de P10 (mensagem vazia).

### 1.4 `.env.example` (opcional, uma palavra)

Na linha 31, trocar "re-cifre as linhas" por "re-cifre as linhas (`audit tenant rotate-keys`)". Sem isso, o comando só aparece documentado na ADR.

### 1.5 Testes de integração (Postgres via testcontainers)

Helper novo ao lado de `_count`, no nível do módulo. Funções do módulo são resolvidas na hora da chamada, então pode ficar depois da classe que usa:

```python
async def _raw_api_key(engine, tenant: Tenant) -> str | None:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                select(tenant_accounts_table.c.broker_api_key_encrypted).where(
                    tenant_accounts_table.c.fiware_service == tenant.fiware_service,
                    tenant_accounts_table.c.fiware_service_path == tenant.fiware_service_path,
                )
            )
        ).scalar_one()
```

Os dois testes entram em `TestKeyRotation`.

**A, o teste que você pediu:**

```python
    @pytest.mark.asyncio
    async def test_rotate_encryption_reencrypts_rows_with_the_first_key(self, engine):
        k1 = Fernet.generate_key()
        k2 = Fernet.generate_key()
        writer = TenantAccountRepository(engine, MultiFernet([Fernet(k1)]))
        await writer.create(
            TENANT_A, broker_url="https://orion.example.com", broker_api_key="chave-secreta"
        )
        await writer.create(TENANT_B, broker_url="https://orion.example.com")
        rotated = TenantAccountRepository(engine, MultiFernet([Fernet(k2), Fernet(k1)]))

        count = await rotated.rotate_encryption()

        raw = await _raw_api_key(engine, TENANT_A)
        assert count == 1
        assert Fernet(k2).decrypt(raw.encode("ascii")) == b"chave-secreta"
        with pytest.raises(InvalidToken):
            Fernet(k1).decrypt(raw.encode("ascii"))
        only_new_key = TenantAccountRepository(engine, MultiFernet([Fernet(k2)]))
        assert (await only_new_key.get_by_tenant(TENANT_A)).broker_api_key == "chave-secreta"
        assert (await only_new_key.get_by_tenant(TENANT_B)).broker_api_key is None
```

O `TENANT_B` sem chave prova que linhas com `NULL` são puladas e não contam (`count == 1`). A leitura com um repositório que só conhece `[k2]` prova que `k1` já pode ser removida.

**B, tudo ou nada:**

```python
    @pytest.mark.asyncio
    async def test_rotate_encryption_is_all_or_nothing_when_a_row_is_undecryptable(self, engine):
        k1 = Fernet.generate_key()
        k2 = Fernet.generate_key()
        k3 = Fernet.generate_key()
        await TenantAccountRepository(engine, MultiFernet([Fernet(k1)])).create(
            TENANT_A, broker_url="https://orion.example.com", broker_api_key="chave-a"
        )
        await TenantAccountRepository(engine, MultiFernet([Fernet(k3)])).create(
            TENANT_B, broker_url="https://orion.example.com", broker_api_key="chave-b"
        )
        rotated = TenantAccountRepository(engine, MultiFernet([Fernet(k2), Fernet(k1)]))

        with pytest.raises(InvalidToken):
            await rotated.rotate_encryption()

        raw_a = await _raw_api_key(engine, TENANT_A)
        assert Fernet(k1).decrypt(raw_a.encode("ascii")) == b"chave-a"
```

Por causa do `order_by`, `smart_city_a` é re-cifrada **antes** de `smart_city_b` falhar. Se ela ainda decifra com `k1` isolada, o rollback aconteceu de fato.

### 1.6 Testes do CLI (sem Docker)

Em `test_cli.py`, no fim do arquivo. `Fernet`/`InvalidToken` não são importados ali hoje, então é preciso acrescentar `from cryptography.fernet import InvalidToken`.

```python
class _FakeTenantAccountRepository:
    def __init__(self, count: int = 0, error: Exception | None = None):
        self._count = count
        self._error = error

    async def rotate_encryption(self) -> int:
        if self._error is not None:
            raise self._error
        return self._count


class TestTenantRotateKeysCommand:
    def test_successful_rotation_prints_count(self, monkeypatch):
        monkeypatch.setattr(
            cli_main, "get_tenant_account_repository", lambda: _FakeTenantAccountRepository(3)
        )

        invocation = runner.invoke(cli_main.app, ["tenant", "rotate-keys"])

        assert invocation.exit_code == 0
        assert "3 linhas" in invocation.stdout

    def test_undecryptable_row_returns_nonzero_exit_with_clear_message(self, monkeypatch):
        monkeypatch.setattr(
            cli_main,
            "get_tenant_account_repository",
            lambda: _FakeTenantAccountRepository(error=InvalidToken()),
        )

        invocation = runner.invoke(cli_main.app, ["tenant", "rotate-keys"])

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "nada foi alterado" in invocation.output

    def test_unexpected_exception_returns_nonzero_exit_without_raw_traceback(self, monkeypatch):
        monkeypatch.setattr(
            cli_main,
            "get_tenant_account_repository",
            lambda: _FakeTenantAccountRepository(error=RuntimeError("BROKER_API_KEY_ENCRYPTION_KEYS nao configurada")),
        )

        invocation = runner.invoke(cli_main.app, ["tenant", "rotate-keys"])

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "BROKER_API_KEY_ENCRYPTION_KEYS nao configurada" in invocation.output
```

---

## 2. `replace_tenant` recusa linha com login

### 2.1 Mudança

- O `RETURNING` passa a pedir só `login_email`.
- Depois do `LookupError`, entra a checagem da recusa.
- O `INSERT` deixa de gravar `login_email`/`password_hash`. As duas colunas ficam `NULL` pelo default da coluna, o que respeita `ck_tenant_accounts_login_pair`.

```python
                    .returning(tenant_accounts_table.c.login_email)
                )
            ).first()
            if deleted is None:
                raise LookupError(
                    f"tenant_account nao encontrado para {old_tenant.fiware_service}"
                    f"/{old_tenant.fiware_service_path}"
                )
            if deleted.login_email is not None:
                raise ValueError(
                    f"tenant_account {old_tenant.fiware_service}"
                    f"/{old_tenant.fiware_service_path} tem login; replace_tenant so' vale "
                    "para contas self-hosted (login e' exclusivo do broker/tenant)"
                )
            await conn.execute(
                tenant_accounts_table.insert().values(
                    fiware_service=new_tenant.fiware_service,
                    fiware_service_path=new_tenant.fiware_service_path,
                    broker_url=broker_url,
                    broker_api_key_encrypted=encrypted_api_key,
                )
            )
```

Sobre a atomicidade: o `ValueError` sai de dentro do `async with self._engine.begin()`, então o `DELETE` é desfeito (P2) e o `INSERT` nunca roda.

### 2.2 Testes (Postgres)

**Reescrever** `test_replace_moves_account_to_new_tenant` para o cenário self-hosted de sucesso:

```python
    @pytest.mark.asyncio
    async def test_replace_moves_self_hosted_account_to_new_tenant(self, repository, engine):
        await repository.create(
            TENANT_A, broker_url="https://orion-1.example.com", broker_api_key="chave-1"
        )

        await repository.replace_tenant(
            TENANT_A, TENANT_C, "https://orion-2.example.com", "chave-2"
        )

        assert await repository.get_by_tenant(TENANT_A) is None
        account_c = await repository.get_by_tenant(TENANT_C)
        assert account_c.broker_url == "https://orion-2.example.com"
        assert account_c.broker_api_key == "chave-2"
        assert account_c.login_email is None
        assert account_c.password_hash is None
        assert await _count(engine) == 1
```

**Novo** teste de recusa, que também prova a atomicidade:

```python
    @pytest.mark.asyncio
    async def test_replace_refuses_account_with_login_and_keeps_row_intact(
        self, repository, engine
    ):
        await repository.create(
            TENANT_A,
            broker_url="https://orion-1.example.com",
            broker_api_key="chave-1",
            login_email="a@x.com",
            password="senha",
        )

        with pytest.raises(ValueError):
            await repository.replace_tenant(
                TENANT_A, TENANT_C, "https://orion-2.example.com", "chave-2"
            )

        account_a = await repository.get_by_tenant(TENANT_A)
        assert account_a.broker_url == "https://orion-1.example.com"
        assert account_a.broker_api_key == "chave-1"
        assert account_a.login_email == "a@x.com"
        assert verify_password("senha", account_a.password_hash) is True
        assert await repository.get_by_tenant(TENANT_C) is None
        assert await _count(engine) == 1
```

Os outros 4 testes de `TestReplaceTenant` usam linhas sem login e continuam valendo sem mudança.

---

## 3. Auditorias antigas: só ADR

Nova seção em `docs/adr/adr-0019.md`, antes de "## Alternativas consideradas":

```markdown
### 6. Auditorias antigas ao trocar broker/tenant

Registros de `audit_runs` (e seus `entity_reports`/`violations`/`recommendations`) de um
tenant/broker que deixou de ser o atual **permanecem no banco sem alteração**, como prova
histórica do que foi auditado. Não há limpeza, cascata nem re-vinculação: `audit_runs` guarda
`tenant_fiware_service`/`tenant_fiware_service_path` e `broker_url` denormalizados, sem FK para
`tenant_accounts`, e `replace_tenant`/`update_broker` só escrevem em `tenant_accounts`. Esse já é
o comportamento natural do esquema; esta seção só o registra como decisão, não como lacuna.
Consequência: um run antigo continua consultável pelo tenant antigo (`GET /audits/{id}` com o
tenant em que foi gravado), não pelo tenant novo.
```

Na mesma ADR, dois ajustes pontuais para refletir as decisões 1 e 2:
- **Seção 1, bullet do `MultiFernet`**: trocar "rotação: colocar a chave nova na frente, re-cifrar as linhas, remover a antiga depois" por "rotação: colocar a chave nova na frente, re-cifrar as linhas com `audit tenant rotate-keys` (`TenantAccountRepository.rotate_encryption()`, uma única transação, tudo ou nada), remover a antiga depois".
- **Seção 2, última frase do bullet da chave**: acrescentar depois de "...nunca um UPDATE de chave primária." o texto "`replace_tenant` recusa (`ValueError`, sem alterar nada) contas com `login_email`: login/senha são exclusivos do broker/tenant SaaS e nunca migram para outro."

---

## 4. `docs/fases/fase-04-integracao-fiware-ngsi.md`, linha 32

Antes:
```
| Variáveis de ambiente | `FIWARE_BROKER_URL`, `FIWARE_API_KEY` |
```
Depois:
```
| Variáveis de ambiente | `FIWARE_BROKER_URL`, `FIWARE_SERVICE`, `FIWARE_SERVICE_PATH` (chave de acesso por tenant: ver [ADR-0019](../adr/adr-0019.md)) |
```
O resto do documento não muda (o entregável da linha 51 continua correto).

---

## 5. Sequência TDD

**Sem Docker** (`pytest tests/unit`):
1. 🔴 Acrescentar `TestTenantRotateKeysCommand` (1.6). Os 3 testes falham porque `cli_main` não tem `get_tenant_account_repository` (o `monkeypatch.setattr` dá `AttributeError`).
2. 🟢 Implementar 1.3 em `main.py`. Os 3 passam. Rodar `tests/unit` inteiro para confirmar que nada mais quebrou.

**Com Postgres via testcontainers** (`pytest tests/integration/persistence/test_tenant_account_repository.py`):

3. 🔴 Acrescentar `_raw_api_key` e os testes A e B (1.5). Falham com `AttributeError: rotate_encryption`.
4. 🟢 Implementar 1.1. A e B passam.
5. 🔴 Reescrever o teste de replace e acrescentar o de recusa (2.2). O de recusa falha (nenhum `ValueError` é levantado). O reescrito já passa, porque o comportamento atual também funciona sem login; ele serve de rede de segurança.
6. 🟢 Implementar 2.1. As 2 passam, e os 4 testes de replace que já existiam continuam verdes.
7. Rodar o arquivo inteiro, depois `tests/integration` inteiro. As 2 falhas conhecidas (`test_pgvector_retriever.py` e `test_run_audit_e2e.py`) continuam iguais e não são tocadas.
8. Documentação (3, 4 e 1.4), sem teste.

## 6. Casos de borda cobertos

- Nenhuma linha com chave: retorna 0, e o CLI imprime "0 linhas".
- Linha com `broker_api_key_encrypted` `NULL`: é pulada e não conta (teste A).
- Linha que nenhuma chave decifra: `InvalidToken`, rollback total (teste B) e mensagem clara no CLI.
- Rodar a rotação duas vezes: funciona, cada rodada re-cifra com IV novo e mesmo resultado lógico. O `rotate()` preserva o timestamp, então TTL (que o projeto nem usa) não seria afetado.
- Chaves não configuradas ou malformadas: a factory levanta `RuntimeError`/`ValueError`, que o CLI mostra sem traceback.
- `update_broker` rodando junto com a rotação: serializado pelo `FOR UPDATE`.
- `replace_tenant` com login e `old == new` (mesmo tenant): também é recusado. O caminho para contas SaaS é `update_broker`.

## 7. Ambiguidades que sobram (não decidi nenhuma)

- **A1**: a rotação não altera `updated_at`. Tratei como troca de material criptográfico, não como mudança de dado. Se quiser que ela apareça em `updated_at`, é acrescentar `updated_at=func.now()` no `.values(...)`.
- **A2**: `update_broker` continua deixando trocar `broker_url`/`api_key` numa linha **com** login. A decisão 2 fala de "trocar o broker mantendo o login", o que pode ou não abranger também o `update_broker` (troca de URL do mesmo cliente, por exemplo migração de host). Não mexi, porque você só decidiu sobre `replace_tenant`.
- **A3**: no self-hosted, a chave fica num arquivo de uma linha só (`selfhosted/fernet-keys.sh`). Rotacionar ali exige editar o arquivo à mão para `k2,k1` e rodar `docker compose run app audit tenant rotate-keys`. Não tem script, fica fora do escopo.
- **A4**: a seção "Consequências → Negativas" da ADR-0019 ainda lista "tabela `tenant_accounts` + migration" como não implementada, o que já está desatualizado. Não corrigi porque não foi pedido.

### Critical Files for Implementation
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/cli/main.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/tests/integration/persistence/test_tenant_account_repository.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/interfaces/cli/test_cli.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/docs/adr/adr-0019.md
