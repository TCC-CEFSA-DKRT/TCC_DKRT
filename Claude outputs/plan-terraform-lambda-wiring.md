# Plano: tornar o modo SaaS implantável na AWS (DEPLOYMENT_MODE, BROKER_API_KEY_ENCRYPTION_KEYS, JWT_SIGNING_KEY)

Repositório lido em `/mnt/user-data/uploads/agent_multi_IA_context_broker`. O **terraform CLI não está instalado** no sandbox (`which terraform` não retorna nada). Por isso nenhum `validate` ou `plan` foi rodado. O `python-hcl2 8.1.4` está instalado no sandbox mas não consta em `requirements.txt` nem em `pyproject.toml`. O `moto` está em `requirements.txt` mas não está instalado.

### 0. O que o código real mostra (três premissas da tarefa estão erradas)

1. **`JWT_SIGNING_KEY` já chega até o Lambda.** A cadeia completa existe:
   - `modules/parameter_store` cria `aws_ssm_parameter.jwt_signing_key` (`/${var.name_prefix}/jwt-signing-key`, SecureString, placeholder, `ignore_changes=[value]`).
   - `environments/production/main.tf` repassa `jwt_signing_key_parameter_name`/`_arn` ao `module.lambda_compute`.
   - `lambda_compute` coloca `JWT_SIGNING_KEY_PARAMETER_NAME` em `local.common_env` e dá `ssm:GetParameter` sobre o ARN.
   - `_bootstrap.bootstrap_settings_from_aws()` mapeia isso para `os.environ["JWT_SIGNING_KEY"]` no module-level dos três handlers, antes de qualquer `Settings()`.

   Falta só o **valor real**, que é um passo manual (item 5).
2. **`FIWARE_BROKER_URL` não passa pelo Parameter Store.** É uma variável Terraform comum (`var.fiware_broker_url` em `production/variables.tf` → `lambda_compute` → `common_env`). Esse é o padrão para valores não-secretos.
3. **O worker é `src/auditor/interfaces/worker/main.py`** (não existe `worker/main.py`). Ele não tem bootstrap nenhum. Lê o `.env` escrito por `modules/compute/user_data/worker.sh.tftpl` (via `EnvironmentFile`) e constrói `Settings()` preguiçosamente, dentro de `container.get_settings()`.

**O que falta de verdade no caminho Lambda (production):**
- `BROKER_API_KEY_ENCRYPTION_KEYS`: não existe parâmetro, nem IAM, nem env var `*_PARAMETER_NAME`, nem mapeamento no `_bootstrap.py`.
- `DEPLOYMENT_MODE`: ausente do `common_env`, então o Lambda sempre roda `selfhosted`.

**Caminho EC2 (homolog):** o `.env` do `api.sh.tftpl`/`worker.sh.tftpl` não tem JWT, chaves nem modo. Além disso, esse caminho já está quebrado por motivos anteriores e independentes do SaaS:
- `database_url_template` (em `modules/database/outputs.tf`) grava literalmente `<SENHA_DO_SECRETS_MANAGER>` no `DATABASE_URL`.
- Os segredos do `modules/secrets` são "containers" sem `aws_secretsmanager_secret_version` e sem leitor no EC2.
- `SQS_DEAD_LETTER_QUEUE_URL` também não vai para o `.env`.

Em production, `modules/compute` só provisiona o Ollama (`provision_api=false`/`provision_worker=false`), que não constrói `Settings`.

**Outras observações:**
- **CI:** `.github/workflows/terraform-and-audit.yml` roda `plan` somente em `environments/academy`, cujo `main.tf` virou um comentário de uma linha (ADR-0018). Production nunca é validado em CI.
- **Formatação:** o `common_env` do `lambda_compute` e o bloco `vpc_endpoints` de production já têm `=` desalinhado. É provável que `terraform fmt -check` já falhe hoje.
- **ADR ausente:** `docs/adr/adr-0018.md` é referenciado mas o arquivo não existe.

### 1. Onde guardar os segredos: Parameter Store SecureString (nada de Secrets Manager)

Justificativa pelo padrão do próprio repositório:
- A ADR-0017 (comentário no topo de `modules/parameter_store/main.tf` e `secrets_bootstrap.py`) decidiu que segredos criados pelo projeto ficam em SSM SecureString com a chave gerenciada `alias/aws/ssm`, sem custo de KMS nem os US$0,40 por segredo/mês.
- O leitor genérico já existe: `load_env_vars_from_parameter_store(mapping)`. O leitor de Secrets Manager existente só serve para o segredo do RDS e monta `DATABASE_URL` especificamente.
- O único ambiente que usa `modules/secrets` é homolog, e lá ninguém lê esses segredos.
- Rotação nativa do Secrets Manager exigiria um Lambda de rotação, o que é exagero. A rotação aqui é manual e rara: `MultiFernet` com a chave nova na frente mais `audit tenant rotate-keys`, e troca da chave JWT.
- Conclusão: `BROKER_API_KEY_ENCRYPTION_KEYS` segue exatamente o padrão de `jwt_signing_key`, e `JWT_SIGNING_KEY` não muda.

### 2. `DEPLOYMENT_MODE`: variável Terraform comum

É um valor não-secreto, então segue o padrão de `FIWARE_BROKER_URL`:
- Criar `var.deployment_mode` (default `"selfhosted"`) em `production/variables.tf` e em `lambda_compute/variables.tf`, esta última com `validation` restrita a `saas`/`selfhosted`.
- Adicionar `DEPLOYMENT_MODE = var.deployment_mode` ao `common_env`.

Parameter Store seria indireção sem ganho: o valor só muda com decisão de deploy, e `terraform apply` já atualiza a configuração do Lambda. Escrever `DEPLOYMENT_MODE=selfhosted` explicitamente é idêntico a omitir a variável, então não é preciso nenhum `merge` condicional.

### 3. Mudanças `.tf` (nomes seguem os existentes)

**`infra/terraform/modules/parameter_store/main.tf`**: novo recurso, cópia do `jwt_signing_key`:
```hcl
resource "aws_ssm_parameter" "broker_api_key_encryption_keys" {
  name        = "/${var.name_prefix}/broker-api-key-encryption-keys"
  description = "Chaves Fernet (lista por virgula; a primeira cifra) de tenant_accounts.broker_api_key_encrypted -- ADR-0019."
  type        = "SecureString"
  value       = var.broker_api_key_encryption_keys
  tags        = var.tags
  lifecycle { ignore_changes = [value] }
}
```
Não mexa no `description` do `jwt_signing_key` existente (que diz "se/quando implementada" e está desatualizado). Um update in-place de um SecureString cujo valor foi definido fora do Terraform é um risco desnecessário.

**`modules/parameter_store/variables.tf`**: `variable "broker_api_key_encryption_keys"` com `default = "REPLACE_AFTER_APPLY"` e `sensitive = true`, mesmo texto de `jwt_signing_key`.

**`modules/parameter_store/outputs.tf`**: `broker_api_key_encryption_keys_parameter_name` e `broker_api_key_encryption_keys_parameter_arn`.

**`modules/lambda_compute/variables.tf`**:
- `broker_api_key_encryption_keys_parameter_name` e `broker_api_key_encryption_keys_parameter_arn`, ambas `string`, sem default, igual às de JWT.
- `deployment_mode`: `string`, default `"selfhosted"`, `validation { condition = contains(["saas","selfhosted"], var.deployment_mode) }`.

**`modules/lambda_compute/main.tf`**:
- No `common_env`: `DEPLOYMENT_MODE = var.deployment_mode` e `BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME = var.broker_api_key_encryption_keys_parameter_name`.
- Na statement `ssm:GetParameter` de `aws_iam_role_policy.lambda_permissions`: acrescentar `var.broker_api_key_encryption_keys_parameter_arn` ao `Resource`.
- Não é preciso `kms:Decrypt`: a chave gerenciada `aws/ssm` autoriza via `kms:ViaService`, e é por esse mesmo caminho que o JWT já funciona.
- Aproveitar para alinhar os `=` do `common_env`.

**`environments/production/variables.tf`**: `variable "deployment_mode"` com default `"selfhosted"` (sem validation; o módulo já valida).

**`environments/production/main.tf`**, no `module "lambda_compute"`:
```hcl
deployment_mode                                = var.deployment_mode
broker_api_key_encryption_keys_parameter_name  = module.parameter_store.broker_api_key_encryption_keys_parameter_name
broker_api_key_encryption_keys_parameter_arn   = module.parameter_store.broker_api_key_encryption_keys_parameter_arn
```

**Não mudam:** `modules/compute/*`, `modules/secrets/*`, `environments/homolog/*`, `environments/academy/*` (descontinuado). Motivos no item 4.

### 4. Como chega às env vars

**Lambda:**
1. `terraform apply` grava `DEPLOYMENT_MODE` e `BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME` no ambiente do Lambda.
2. No cold start, `_bootstrap.bootstrap_settings_from_aws()` chama o SSM.
3. O valor decifrado vai para `os.environ["BROKER_API_KEY_ENCRYPTION_KEYS"]`.
4. `Settings()` lê essa variável.

A mudança em `src/auditor/interfaces/aws_lambda/_bootstrap.py` é mais um `if`, no mesmo formato dos dois existentes:
```python
if "BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME" in os.environ:
    parameter_names_by_env_var["BROKER_API_KEY_ENCRYPTION_KEYS"] = os.environ[
        "BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME"
    ]
```
Um ponto de simplificação opcional, que fica a critério de quem implementar: trocar os três `if` por um loop sobre a tupla `("ORION_CREDENTIALS_JSON", "JWT_SIGNING_KEY", "BROKER_API_KEY_ENCRYPTION_KEYS")` com o nome `f"{...}_PARAMETER_NAME"`. Mas `ORION_CREDENTIALS_JSON` vem de `ORION_CREDENTIALS_PARAMETER_NAME`, que não segue esse formato de nome, então o `if` extra é o diff menor.

**Compatibilidade self-hosted:**
- `DEPLOYMENT_MODE` ausente ou igual a `selfhosted` resulta no default do `Settings`.
- A chave placeholder carregada no processo não é usada em `selfhosted`: `get_context_broker()` não chama `get_tenant_account_repository()`, e o router `auth` só é montado em `saas` (`app.py:113`).
- homolog e academy não instanciam `lambda_compute`, então não são afetados.

**EC2:** em production é só o Ollama, que não constrói `Settings`. Em homolog (API e worker em EC2) nada muda: sem `DEPLOYMENT_MODE`, fica `selfhosted`, que é o comportamento de hoje. Ligar SaaS no EC2 exigiria buscar segredos no boot da instância, e esse caminho já não conecta nem ao banco (placeholder de senha). Isso fica como ambiguidade A2; não está incluído aqui.

**Docstring:** o `load_env_vars_from_parameter_store` em `src/auditor/infrastructure/config/secrets_bootstrap.py` diz "Settings ainda NAO le nenhum dos dois ... nao ha' nenhum consumidor downstream". Isso está falso para `JWT_SIGNING_KEY` e passa a ser falso para as chaves Fernet. Corrigir para dizer que `JWT_SIGNING_KEY` e `BROKER_API_KEY_ENCRYPTION_KEYS` são consumidos pelo `Settings` e que `ORION_CREDENTIALS_JSON` continua sem consumidor (item 6).

### 5. Placeholder `REPLACE_AFTER_APPLY` (runbook, sem código)

As salvaguardas já existem:
- **JWT placeholder em `saas`:** o `ValueError` no `Settings()` faz o `create_app()` (module-level do `api_handler`) falhar no init. A API não sobe e o erro aparece no CloudWatch.
- **Chave Fernet placeholder:** `Fernet("REPLACE_AFTER_APPLY")` levanta `ValueError` em `get_tenant_account_repository()` (já testado em `test_factory_rejects_a_malformed_key`).

Documentar em `docs/adr/adr-0019.md` (seção de implantação) ou no README, nesta ordem:
1. `terraform apply` com `deployment_mode` no default `selfhosted`. Os parâmetros nascem com o placeholder.
2. Gravar os valores reais:
   ```
   aws ssm put-parameter --name /auditor-prod/jwt-signing-key --type SecureString --overwrite \
     --value "$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
   aws ssm put-parameter --name /auditor-prod/broker-api-key-encryption-keys --type SecureString --overwrite \
     --value "$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
   ```
   O `ignore_changes=[value]` preserva esses valores nos applies seguintes.
3. `terraform apply -var deployment_mode=saas`. A mudança de configuração do Lambda força cold starts novos, que leem os valores reais.

**Rotação:**
- **Fernet:** `put-parameter` com `"NOVA,ANTIGA"`, forçar cold start, rodar `audit tenant rotate-keys`, depois `put-parameter` com `"NOVA"` e novo cold start.
- **JWT:** `put-parameter` e cold start. Todos os tokens emitidos são invalidados, com impacto de no máximo `jwt_expiration_minutes` (default 60).
- **Forçar cold start:** Lambdas já quentes mantêm o valor antigo até serem reciclados. Um `aws lambda update-function-configuration` (por exemplo, trocando `--description`) nas três funções força ambientes novos. Validar isso na conta real; não foi testado aqui.

### 6. `ORION_CREDENTIALS_JSON` / `secrets_bootstrap.py`: situação atual (sem decisão)

- **Lambda (production):** existem `aws_ssm_parameter.orion_credentials`, a env var `ORION_CREDENTIALS_PARAMETER_NAME`, a permissão IAM e o mapeamento no `_bootstrap.py`. O valor é decifrado para `os.environ["ORION_CREDENTIALS_JSON"]`, mas `Settings` não tem esse campo (`extra="ignore"`) e nada lê a variável.
- **EC2 (homolog):** `module.secrets.orion_credentials_secret_arn` recebe permissão IAM de leitura, mas ninguém lê esse segredo e ele nunca recebeu valor.
- **`secrets_bootstrap.py`** continua necessário de qualquer forma: é ele que monta `DATABASE_URL` a partir do segredo do RDS e carrega o JWT (e, com este plano, as chaves Fernet). Só o mapeamento `ORION_CREDENTIALS_JSON` está morto.
- Com a ADR-0019, credenciais de broker em SaaS vivem cifradas em `tenant_accounts`. Em selfhosted, `OrionAdapter` não recebe `api_key`.

Caminhos possíveis, para o usuário decidir:
- **(A) Remover** o caminho de ponta a ponta no Lambda: recurso, variável e outputs do `parameter_store`; variáveis, env e IAM do `lambda_compute`; argumentos em production; o `if` no `_bootstrap.py`. Opcionalmente, também o `orion_credentials` do `modules/secrets` e do `compute`/homolog. O próximo apply destrói o parâmetro, o que é inofensivo porque ele só guarda o placeholder. Deve ser um commit separado deste.
- **(B) Reaproveitar** como `api_key` do broker único num deploy selfhosted na AWS. Exige código novo (campo no `Settings` e `OrionAdapter` com api_key em selfhosted) e contradiz a ADR-0019, que diz que selfhosted grava a configuração em `tenant_accounts`.
- Ficar como está é o status quo: dead code documentado.

### 7. Testes sem `terraform apply`

**T1: `tests/unit/interfaces/aws_lambda/test_lambda_bootstrap.py`** (arquivo e pasta novos; o nome evita colisão, porque `tests/` não tem `__init__.py`).
- Isolar o ambiente com um fixture que usa `unittest.mock.patch.dict(os.environ, {...}, clear=True)`. `monkeypatch.delenv(raising=False)` não restaura variáveis que o bootstrap cria do zero, porque grava direto em `os.environ`.
- Substituir `auditor.infrastructure.config.secrets_bootstrap._default_ssm_client` via `monkeypatch.setattr` por um fake com `get_parameter(Name, WithDecryption)` que devolve `{"Parameter": {"Value": ...}}` e registra as chamadas.
- Importar somente `auditor.interfaces.aws_lambda._bootstrap`. Nunca importar os handlers: eles rodam bootstrap e `create_app()` no import.
- Casos:
  1. `BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME` presente → `os.environ["BROKER_API_KEY_ENCRYPTION_KEYS"]` recebe o valor do SSM, com `WithDecryption=True`. **Falha hoje.**
  2. Ambiente igual ao do Lambda (`DEPLOYMENT_MODE=saas` mais os parâmetros de JWT e chaves; o fake devolve um token de 48 caracteres e `Fernet.generate_key()`), depois `Settings(_env_file=None)` → `deployment_mode == "saas"` e `broker_api_key_encryption_keys_list == [chave]`. **Falha hoje.**
  3. Regressão selfhosted: nenhum `*_PARAMETER_NAME` e nenhum `DEPLOYMENT_MODE` → o fake de SSM não é chamado (a factory levanta `AssertionError` se for) e `Settings(_env_file=None).deployment_mode == "selfhosted"`. Passa hoje e deve continuar passando.

**T2: `tests/unit/infrastructure/test_terraform_saas_wiring.py`**, com `hcl2 = pytest.importorskip("hcl2")` para não quebrar um ambiente sem a lib. Substitui o `terraform validate` que não pode ser rodado aqui.
- Formato confirmado no hcl2 8.1.4:
  - rótulos de bloco vêm com aspas (`'"aws_ssm_parameter"'`, `'"jwt_signing_key"'`);
  - literais vêm com aspas (`'"sqs"'`);
  - interpolações vêm como `'${var.x}'`;
  - `lifecycle` é uma lista de dicts;
  - `variable` é uma lista de `{'"nome"': {...}}`.

  Um helper `strip('"')` resolve.
- Asserções:
  1. `parameter_store` tem `aws_ssm_parameter.broker_api_key_encryption_keys` com `type` SecureString e `ignore_changes` contendo `value`, e os dois outputs novos.
  2. `lambda_compute`: o `common_env` contém `DEPLOYMENT_MODE` e `BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME`; `deployment_mode` tem default `selfhosted`; a policy serializada contém `var.broker_api_key_encryption_keys_parameter_arn`.
  3. Guarda de segurança: nenhuma chave do `common_env` é `JWT_SIGNING_KEY` ou `BROKER_API_KEY_ENCRYPTION_KEYS` em texto puro; só as variantes `*_PARAMETER_NAME`.
  4. Checagem genérica de variáveis de módulo, que imita o `validate`: em `production/main.tf`, para `lambda_compute` e `parameter_store`, todo argumento passado existe como `variable` no módulo, e toda `variable` sem default é passada.

**Opcional, com o usuário (A4):** um job de CI com `terraform init -backend=false && terraform validate && terraform fmt -check` em `environments/production`. Não precisa de credenciais AWS.

Comando de verificação local: `pytest tests/unit/interfaces/aws_lambda tests/unit/infrastructure tests/unit/infrastructure/config -q`, depois a suíte completa.

### 8. Sequência de implementação

1. **RED Python:** escrever T1 (casos 1 e 2 falham; o 3 passa).
2. **GREEN Python:** adicionar o `if` no `_bootstrap.py` e corrigir o docstring de `load_env_vars_from_parameter_store`.
3. **RED Terraform:** escrever T2 (as asserções 1, 2 e 4 falham; a 3 passa).
4. **GREEN Terraform:**
   1. `parameter_store` (`main.tf`, `variables.tf`, `outputs.tf`);
   2. `lambda_compute` (`variables.tf`, `main.tf`, incluindo o alinhamento do `common_env`);
   3. `production` (`variables.tf`, `main.tf`).
5. Suíte completa.
6. Documentar o runbook do item 5 em `docs/adr/adr-0019.md` e acrescentar `DEPLOYMENT_MODE` e o parâmetro de chaves ao cabeçalho de `environments/production/main.tf`.
7. (Separado, só se o usuário decidir A1 ou A4) remoção do `ORION_CREDENTIALS_JSON` e/ou job de CI.

### 9. Arquivos

**Criados:**
- `tests/unit/interfaces/aws_lambda/test_lambda_bootstrap.py`
- `tests/unit/infrastructure/test_terraform_saas_wiring.py`

**Alterados:**
- `src/auditor/interfaces/aws_lambda/_bootstrap.py`
- `src/auditor/infrastructure/config/secrets_bootstrap.py` (só o docstring)
- `infra/terraform/modules/parameter_store/{main,variables,outputs}.tf`
- `infra/terraform/modules/lambda_compute/{main,variables}.tf`
- `infra/terraform/environments/production/{main,variables}.tf`
- `docs/adr/adr-0019.md` (runbook)

**Não alterados:** `modules/compute`, `modules/secrets`, `environments/homolog`, `environments/academy`, `src/auditor/interfaces/worker/main.py`, `settings.py`, `container.py`.

### 10. Ambiguidades para o usuário (não decidir)

- **A1:** o que fazer com `ORION_CREDENTIALS_JSON`: remover, reaproveitar ou manter (item 6). Vale também para o `orion_credentials` do `modules/secrets` e do `compute` em homolog.
- **A2:** SaaS deve ser implantável também em homolog (EC2)? Isso exigiria corrigir antes o `DATABASE_URL` com placeholder de senha e buscar segredos no boot da instância. A alternativa é declarar "SaaS = somente production/Lambda".
- **A3 (bloqueia o uso real do SaaS):** onde o operador roda `audit tenant register` e `audit tenant rotate-keys` em production. O RDS está em subnet privada e o SG só aceita as SGs de API/worker EC2 e do Lambda; não há bastion nem task administrativa. Sem isso não dá para cadastrar o primeiro tenant nem concluir uma rotação de chave.
- **A4:** incluir o job de CI `init -backend=false` + `validate` para production e trocar o `plan` da academy (que está morto)? E consertar o `fmt`, que provavelmente já falha?
- **A5:** adicionar `python-hcl2` às dependências de dev (o T2 hoje depende de `importorskip`, e sem a lib ele é pulado, não falha)?
- **A6:** onde fica o runbook (ADR-0019, README ou `docs/fases/fase-10-*`) e se ele deve registrar que o arquivo `adr-0018.md` está faltando.

### Critical Files for Implementation
- /mnt/user-data/uploads/agent_multi_IA_context_broker/infra/terraform/modules/lambda_compute/main.tf
- /mnt/user-data/uploads/agent_multi_IA_context_broker/infra/terraform/modules/parameter_store/main.tf
- /mnt/user-data/uploads/agent_multi_IA_context_broker/infra/terraform/environments/production/main.tf
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/aws_lambda/_bootstrap.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/infrastructure/config/secrets_bootstrap.py
