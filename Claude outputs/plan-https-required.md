# Plano: exigir HTTPS no `broker_url` do tenant quando `DEPLOYMENT_MODE=saas`

A validação fica em Python, dentro do `TenantAccountRepository`, e só liga no modo `saas`. Não vai ter `CHECK` de banco. O motivo está no código: `tenant_accounts` não é só do SaaS.

## 1. Onde validar

**`CHECK` de banco não serve aqui, nem como segunda camada.** O banco não sabe em qual modo a aplicação está rodando. A ADR-0019 §2 (`docs/adr/adr-0019.md`, linhas 108-111 e 127-131) define que o bundle self-hosted usa **a mesma tabela `tenant_accounts`**. A futura tela de Configuração vai gravar nela via `replace_tenant`/`update_broker`, e o Orion do produtor normalmente é `http://orion:1026` na rede local. Um `CHECK (broker_url LIKE 'https://%')` quebraria exatamente o que você disse que não pode ser afetado. Por isso também não entra migration nova.

**A validação vai no repositório, ligada por uma flag no construtor.** Os três métodos de escrita passam por ele. O repositório não lê `Settings`, então o container informa o modo:

- `TenantAccountRepository.__init__(self, engine, fernet, require_https: bool = False)`. O default `False` mantém self-hosted e todos os testes atuais iguais.
- `get_tenant_account_repository()` (`container.py:84`) passa `require_https=get_settings().deployment_mode == "saas"`.
- Um helper privado, chamado **na primeira linha** de cada método de escrita, antes de cifrar e antes de abrir a transação:
  ```python
  def _check_broker_url(self, broker_url: str) -> None:
      if self._require_https and not broker_url.startswith("https://"):
          raise ValueError("DEPLOYMENT_MODE=saas exige broker_url com https:// (ex.: https://orion.exemplo.com)")
  ```

Sobre o caminho de escrita que "escaparia": hoje não existe nenhum. O único código que grava `broker_url` é esse repositório, e o Lambda admin só executa os mesmos comandos Typer (`CliRunner().invoke(app, argv)`), que usam a mesma factory.

## 2. Mensagem de erro

A CLI não precisa mudar. O `except Exception as exc` em `cli/main.py` (linhas 255-257) já imprime `Erro ao registrar tenant: {exc}` e sai com código 1. O operador vai ver:

```
Erro ao registrar tenant: DEPLOYMENT_MODE=saas exige broker_url com https:// (ex.: https://orion.exemplo.com).
```

De propósito, a mensagem **não repete a URL recebida**. Se o operador colar `http://user:senha@host`, a credencial acabaria no `output` do Lambda e, dali, no CloudWatch.

## 3. Quais métodos validam

Os três: `create`, `update_broker` e `replace_tenant`.
- No modo saas, `TenantRoutedContextBroker` usa como destino qualquer linha da tabela, com ou sem login. Não tem por que uma linha `http://` ser aceita só porque entrou por outro método.
- `update_broker` e `replace_tenant` ainda não têm chamador em produção (só testes e a futura tela self-hosted). Mesmo assim, uma linha em cada um custa menos do que deixar a brecha para depois.
- No `replace_tenant`, a validação **tem que vir antes do `DELETE`**. Se viesse depois, a transação daria rollback de qualquer forma, mas validar antes é mais claro e o teste abaixo prova isso.
- `rotate_encryption` não escreve `broker_url`, então fica de fora.

## 4. Sequência TDD

**a) Teste unitário do repositório, sem Postgres.** Novo arquivo `tests/unit/infrastructure/persistence/test_tenant_account_broker_url.py`. Como a validação acontece antes de qualquer I/O, dá para passar `engine=None` e um `MultiFernet([Fernet(Fernet.generate_key())])`. Com isso o teste também prova que nada chega ao banco.
- `require_https=True`: `create`, `update_broker` e `replace_tenant` com `http://orion:1026` levantam `ValueError` com `"https://"` na mensagem. Se `replace_tenant` chegasse no `DELETE`, estouraria `AttributeError` em `None.begin()` em vez de `ValueError`, então o teste prova que ele recusa antes do `DELETE`.
- `require_https=True` com `https://...` não levanta `ValueError`. Aqui o `engine=None` estoura depois: usar `pytest.raises(AttributeError)`, ou testar só o helper. Prefiro testar `_check_broker_url` direto.
- `require_https=False` com `http://` passa pelo helper sem erro (self-hosted preservado).

Rodar e ver falhar: o construtor ainda não aceita `require_https`.

**b) Teste da factory.** Em `tests/unit/infrastructure/config/test_tenant_account_repository_factory.py`, dois casos:
- `DEPLOYMENT_MODE=saas` resulta em `repository._require_https is True`. O validator do `Settings` exige também `JWT_SIGNING_KEY` com pelo menos 32 bytes no env.
- Sem `DEPLOYMENT_MODE` (default `selfhosted`) resulta em `False`.

O arquivo já usa `_clear_caches` e testa `repository._fernet`, então acessar o atributo privado segue o padrão existente.

**c) Implementar:** o construtor, o helper, as três chamadas e a linha no container. Rodar `pytest tests/unit -q`.

**d) Regressão de integração:** `pytest -m integration tests/integration/persistence/test_tenant_account_repository.py tests/integration/context_broker/`. Todas as fixtures ali já usam `https://` e o default é `False`, então nada deve quebrar.

Não precisa de teste novo na CLI: `test_c7_generic_exception_returns_nonzero_exit_without_traceback` já cobre o caminho `ValueError` → exit 1 sem traceback.

## 5. Arquivos

| Arquivo | Mudança |
|---|---|
| `src/auditor/infrastructure/persistence/tenant_account_repository.py` | parâmetro `require_https`, `_check_broker_url` e 3 chamadas |
| `src/auditor/infrastructure/config/container.py` | `get_tenant_account_repository` passa a flag (1 linha) |
| `tests/unit/infrastructure/persistence/test_tenant_account_broker_url.py` | **novo** |
| `tests/unit/infrastructure/config/test_tenant_account_repository_factory.py` | +2 testes |
| `docs/adr/adr-0019.md` | 1 frase na seção SaaS: "`broker_url` exige `https://` em `saas`, validado na aplicação, não no banco, porque self-hosted usa a mesma tabela com `http://` local" |

Sem migration. `cli/main.py` e `admin_handler.py` ficam como estão.

## 6. Ambiguidades para você decidir

1. **Linhas `http://` que já estejam no banco de produção.** A regra só vale para gravações novas; a leitura continua funcionando. Se produção já tem tenants cadastrados, vale conferir com `SELECT ... WHERE broker_url NOT LIKE 'https://%'` e corrigir à mão. Não vale uma migration de dados para isso.
2. **Maiúsculas no esquema.** `startswith("https://")` recusa `HTTPS://...`. Segue ao pé da letra "deve começar com `https://`" e a mensagem já mostra o formato certo. Se quiser aceitar maiúsculas, é trocar por `broker_url.lower().startswith(...)`.

### Critical Files for Implementation
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/persistence/tenant_account_repository.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/container.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/config/test_tenant_account_repository_factory.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/cli/main.py (somente leitura: confirma que o `except Exception` já mostra a mensagem)
- /mnt/user-data/uploads/agent_multi_IA_context_broker/docs/adr/adr-0019.md
