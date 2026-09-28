# Plano A3: acesso administrativo ao RDS de produção

**Recomendação:** criar um quarto Lambda, `${name_prefix}-admin`, na mesma imagem, VPC, security group e role do Lambda da API. O operador invoca esse Lambda com `aws lambda invoke`, e ele roda os comandos Typer em processo. Isso não exige nenhuma mudança de rede nem de security group, e não custa nada quando está ocioso.

Um achado pesa mais que a escolha da abordagem: **o RDS de produção não tem schema.** A imagem Lambda não inclui `alembic.ini` nem `migrations/`, e nada roda `alembic upgrade head` em produção. Hoje, `tenant register` falharia com "relation tenant_accounts does not exist". O mesmo Lambda precisa então aplicar as migrations.

O `terraform` não está instalado no sandbox (`which terraform` não retornou nada). O próprio `environments/production/main.tf` registra que `releases.hashicorp.com` é bloqueado pelo proxy e que produção nunca passou por `terraform plan`. A validação continua sendo por `python-hcl2`, que está instalado (8.1.4). O `boto3>=1.34.0` já está em `requirements.txt` e no `pyproject.toml`. `typer`, `alembic` e `click` também já estão na imagem.

## 1. Comparação das abordagens (com fatos do repo)

| | Rede e SG | IAM | Código da app no host | Custo ocioso | Esforço |
|---|---|---|---|---|---|
| **2. Lambda admin** | **Nada a mudar.** O SG `aws_security_group.lambda` já tem `aws_security_group_rule.rds_from_lambda` (5432). O SG dos endpoints (`vpce-sg`) já aceita esse SG. O NAT (`enable_nat_gateway = true`) já cobre o Secrets Manager. | Pode reusar `aws_iam_role.lambda_execution`, que já tem `ssm:GetParameter` nos 3 parâmetros e `secretsmanager:GetSecretValue` no segredo do RDS. | Já está lá: mesma imagem, `_bootstrap.bootstrap_settings_from_aws()`, mesmo `local.common_env`. | 0 | Mínimo |
| 1. Bastion + SSM | Novo EC2, nova regra de ingress no SG do banco. `modules/vpc_endpoints` só tem `sqs` e `ssm`; faltam `ssmmessages` e `ec2messages`, ou o bastion vai para a subnet pública. | Nova role com `AmazonSSMManagedInstanceCore`, mais os mesmos acessos ao Parameter Store e ao Secrets Manager. | Não: seria preciso instalar Python, o repo e reproduzir o bootstrap. | Pequeno (EBS), e a instância fica liga/desliga | Alto |
| 3. Fargate | Novo SG ou reuso do SG do Lambda. | Execution role, task role e cluster novos. | A imagem é `public.ecr.aws/lambda/python:3.11`, então o entrypoint teria que ser sobrescrito. | ~0 | O mais alto |
| 4. SSM na EC2 do Ollama | Precisa de nova regra de ingress no SG do banco. A instância fica na **subnet pública** (`public_subnet_id`), com SG que já abre a porta 22 para `0.0.0.0/0`. | `aws_iam_role_policy.instance_policy` não tem SSM. | Não tem: a instância só roda Ollama. | g4dn.xlarge, desligada por padrão pelos scripts start/stop. Seria preciso ligar uma GPU só para cadastrar um tenant. | Médio, e mistura responsabilidades |
| 5a. RDS Data API | Não se aplica: só funciona com Aurora, e este RDS é Postgres comum (`aws_db_instance`). | | | | |
| 5b. Endpoint HTTP admin no ALB | Expõe a operação administrativa na internet. Pior superfície de ataque. | | | | |

O limite de 15 minutos do Lambda não pesa aqui. `register` é um único INSERT, e `rotate_encryption()` é uma transação só. O cold start leva poucos segundos e só acontece em operações raras.

## 2. Mudanças Terraform

**`infra/terraform/modules/lambda_compute/main.tf`**, seguindo o padrão exato de `worker_dlq`:

```hcl
resource "aws_cloudwatch_log_group" "admin" {
  name              = "/aws/lambda/${var.name_prefix}-admin"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# A3: comandos administrativos (audit tenant register/rotate-keys, migrations)
# contra o RDS privado. Sem aws_lambda_permission, function URL, event source
# mapping ou target group: só um principal IAM com lambda:InvokeFunction
# nesta ARN (aws_iam_policy.admin_invoke) consegue invocar.
resource "aws_lambda_function" "admin" {
  function_name = "${var.name_prefix}-admin"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = local.image_uri

  image_config {
    command = ["auditor.interfaces.aws_lambda.admin_handler.handler"]
  }

  timeout     = 900 # máximo do Lambda; invocação manual e rara, sem ALB para respeitar
  memory_size = var.worker_memory_mb

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id] # já liberado no RDS por rds_from_lambda
  }

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.admin, aws_iam_role_policy_attachment.vpc_access]
  tags       = merge(var.tags, { Name = "${var.name_prefix}-admin" })
}

resource "aws_iam_policy" "admin_invoke" {
  name        = "${var.name_prefix}-admin-invoke"
  description = "Permite invocar SOMENTE o Lambda administrativo (A3). Anexar ao usuário/grupo do operador."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.admin.arn
    }]
  })
  tags = var.tags
}
```

**`modules/lambda_compute/outputs.tf`:** acrescentar `admin_function_name` (`aws_lambda_function.admin.function_name`) e `admin_invoke_policy_arn` (`aws_iam_policy.admin_invoke.arn`).

**`environments/production/outputs.tf`:** acrescentar `admin_function_name` e `admin_invoke_policy_arn`, repassando `module.lambda_compute.*`.

**`environments/production/main.tf`:** nada muda. Não há variável nova no módulo nem regra de SG nova. O `vpc_endpoints` também não muda.

Escolhas deliberadamente mais simples:
- **Role compartilhada.** O Lambda admin herda permissões de SQS que não usa. Criar uma role dedicada seria só redução de privilégio (ver seção 9).
- **Sem variáveis de timeout ou memória para o admin.** O timeout fica fixo em 900, e a memória reusa `worker_memory_mb`, porque é a mesma imagem e os mesmos imports.

## 3. Código Python

**Novo arquivo `src/auditor/interfaces/aws_lambda/admin_handler.py`**, no mesmo padrão dos outros handlers (bootstrap no module-level, imports com `# noqa: E402`):

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from auditor.interfaces.aws_lambda._bootstrap import bootstrap_settings_from_aws

bootstrap_settings_from_aws()

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from auditor.infrastructure.config.container import get_engine  # noqa: E402
from auditor.interfaces.cli.main import app  # noqa: E402

_TASK_ROOT = Path(os.environ.get("LAMBDA_TASK_ROOT", "."))


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    argv = event["argv"]  # nunca logar: carrega --password/--broker-api-key
    try:
        if argv == ["migrate"]:
            cfg = Config(str(_TASK_ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(_TASK_ROOT / "migrations"))
            command.upgrade(cfg, "head")
            return {"exit_code": 0, "output": "migrations aplicadas (head)\n"}
        result = CliRunner().invoke(app, argv)
        return {"exit_code": result.exit_code, "output": result.output}
    finally:
        # ponytail: get_engine() é lru_cache e cada comando CLI faz o próprio asyncio.run;
        # num warm start o pool ficaria preso ao loop fechado. dispose(close=False) só
        # descarta o pool. Upgrade: criar engine por invocação, se virar hot path.
        if get_engine.cache_info().currsize:
            get_engine().sync_engine.dispose(close=False)
```

Por que `CliRunner` e não chamar as funções direto:
- Reusa 100% dos comandos reais, inclusive a validação e o tratamento de erro de `tenant_register` (`_REGISTER_CONSTRAINT_MESSAGES`, `InvalidToken`, e assim por diante).
- Captura stdout e stderr em memória. A "Senha inicial (exibida uma unica vez)" volta **só na resposta** da invocação e nunca vai para o CloudWatch.
- Converte erro de uso (opção faltando) em `exit_code=2`, sem lançar exceção.

Testei isso localmente com typer 0.27.2 e click 8.5.0. Uso `result.output` (stdout e stderr juntos) em vez de `result.stderr`, porque `.stderr` quebra em click < 8.2 com o `mix_stderr` padrão, e o `requirements.txt` não fixa a versão do click.

**`Dockerfile`**, depois do `COPY src/auditor ...`:

```dockerfile
COPY alembic.ini ${LAMBDA_TASK_ROOT}/alembic.ini
COPY migrations ${LAMBDA_TASK_ROOT}/migrations
```

O `migrations/env.py` já lê `DATABASE_URL` do ambiente, e essa variável é populada pelo bootstrap a partir do segredo gerenciado pelo RDS. É o mesmo caminho de `tests/integration/persistence/test_migrations.py`, que usa `command` com `Config`.

## 4. Testes sem `terraform apply`

**Novo `tests/unit/interfaces/aws_lambda/test_admin_handler.py`.** Não configurar nenhuma variável `*_PARAMETER_NAME` ou `DB_MASTER_USER_SECRET_ARN`, para que o bootstrap vire no-op (o mesmo que `test_selfhosted_regression_does_not_call_ssm` já garante). Usar o mesmo `monkeypatch` em `cli_main.get_tenant_account_repository` que `tests/unit/interfaces/cli/test_cli.py` já usa:

1. `handler({"argv": ["tenant", "rotate-keys"]}, None)` com um repositório fake que retorna 3 → `exit_code == 0` e "Chaves rotacionadas: 3" em `output`.
2. `tenant register ... --email x@y` sem `--password` → "Senha inicial" em `output` e **ausente** de `capsys.readouterr().out`. É a garantia de que a senha não vaza para o CloudWatch.
3. `argv` com opção obrigatória faltando → `exit_code == 2`, sem exceção.
4. `["migrate"]` com `admin_handler.command.upgrade` trocado por um gravador → chamado com `"head"`, e o `script_location` do config termina em `migrations`.
5. O `Dockerfile` contém `COPY alembic.ini` e `COPY migrations`. É uma verificação por string, porque sem isso o `migrate` quebra só em runtime.

**Nova classe `TestAdminLambda` em `tests/unit/infrastructure/test_terraform_saas_wiring.py`**, reusando `_load`, `_find_resource` e `_unquote`:
- `aws_lambda_function.admin` → `image_config[0].command` é igual a `["auditor.interfaces.aws_lambda.admin_handler.handler"]`.
- `vpc_config` referencia `aws_security_group.lambda.id` e `var.private_subnet_ids`; `environment` usa `local.common_env`.
- Nenhum `aws_lambda_permission`, `aws_lambda_function_url` ou `aws_lambda_event_source_mapping` em `main.tf` referencia `aws_lambda_function.admin`.
- A string de `aws_iam_policy.admin_invoke.policy` contém `lambda:InvokeFunction` e `aws_lambda_function.admin.arn`, e não contém `"*"`.
- As outputs do módulo e de `production/outputs.tf` expõem `admin_function_name` e `admin_invoke_policy_arn`.
- Guarda de regressão: em `production/main.tf` continua existindo **exatamente uma** `aws_security_group_rule` com `security_group_id = module.network.database_sg_id`, ou seja, o SG do RDS não foi aberto.

Os testes de wiring já parametrizados de `lambda_compute` continuam passando, porque o módulo não ganha variável obrigatória nova.

## 5. Segurança

- **Quem pode invocar:** não há política baseada em recurso no Lambda, então nenhum serviço nem conta externa pode invocá-lo. Dentro da conta, só quem tiver `lambda:InvokeFunction` nessa ARN, que é o papel da `aws_iam_policy.admin_invoke`. O anexo a um usuário, grupo ou permission set fica manual (seção 9).
- **Ressalva:** qualquer principal que já tenha `lambda:*` em `*` (administradores da conta) também consegue invocar. Não dá para negar isso pela política do recurso, porque Lambda resource policies não bloqueiam principais da mesma conta com Allow em identidade.
- **Porta nenhuma aberta.** O SG do RDS continua com `api`, `worker` e `rds_from_lambda`. Não há porta 22, bastion nem IP público.
- **Segredos no payload:** o handler nunca loga o `event`. O payload de Invoke não aparece no CloudTrail. O `CliRunner` evita que a senha gerada passe pelo stdout do Lambda. No lado do operador, o arquivo de payload e o de resposta contêm segredos: `umask 077` e `rm` depois (está no runbook).
- **Trilha de auditoria:** quem invocou aparece no CloudTrail só se os data events de Lambda estiverem ligados (seção 9).

## 6. Runbook

```bash
cd infra/terraform/environments/production
FN=$(terraform output -raw admin_function_name)   # ex.: auditor-prod-admin
umask 077

# helper: invoca, mostra saída e exit_code, apaga a resposta
admin() {
  aws lambda invoke --function-name "$FN" --cli-read-timeout 0 \
    --payload "fileb://$1" /tmp/admin-out.json >/dev/null \
  && jq -r '.output // ., "exit_code=\(.exit_code // "erro")"' /tmp/admin-out.json
  rm -f /tmp/admin-out.json "$1"
}

# 0) uma vez por deploy com migration nova (e ANTES do primeiro tenant)
echo '{"argv":["migrate"]}' > /tmp/p.json && admin /tmp/p.json

# 1) cadastrar tenant SaaS (senha gerada volta uma única vez na saída)
cat > /tmp/p.json <<'EOF'
{"argv":["tenant","register","--tenant","acme","--broker-url","https://orion.acme.com",
 "--broker-api-key","<API_KEY>","--email","ops@acme.com"]}
EOF
admin /tmp/p.json

# 2) rotação Fernet (estende ADR-0019: agora são QUATRO funções)
aws ssm put-parameter --name <param broker-api-key-encryption-keys> --type SecureString \
  --overwrite --value "NOVA,ANTIGA"
for f in api worker worker-dlq admin; do
  aws lambda update-function-configuration --function-name auditor-prod-$f --description "cold $(date +%s)" >/dev/null
  aws lambda wait function-updated --function-name auditor-prod-$f
done
echo '{"argv":["tenant","rotate-keys"]}' > /tmp/p.json && admin /tmp/p.json
aws ssm put-parameter ... --overwrite --value "NOVA"
# repetir o loop de cold start
```

O cold start do `-admin` é obrigatório antes do `rotate-keys`. Um container quente guarda a lista antiga de chaves, porque o bootstrap nunca sobrescreve uma variável de ambiente já presente, e nesse caso ele re-cifraria com a chave velha.

`--cli-read-timeout 0` é necessário porque o AWS CLI desiste depois de 60 segundos por padrão.

Um erro não tratado (por exemplo, falha no `migrate`) aparece como `FunctionError`, e o JSON de resposta traz `errorMessage` no lugar de `output`.

## 7. Sequência de implementação

1. RED: `test_admin_handler.py`, com os testes 1 a 5 da seção 4.
2. GREEN: `admin_handler.py` e as duas linhas `COPY` no `Dockerfile`.
3. RED: `TestAdminLambda` nos testes de wiring.
4. GREEN: `lambda_compute/main.tf` (log group, função e política), `lambda_compute/outputs.tf` e `production/outputs.tf`.
5. `pytest tests/unit` para confirmar que não há regressão em `test_lambda_bootstrap.py`, `test_cli.py` nem nos testes de wiring.
6. Docs: na seção de rotação da `docs/adr/adr-0019.md`, trocar "três funções" por quatro e apontar para o runbook acima.
7. Deploy real (fora do sandbox): `docker build && docker push` da imagem nova, `terraform apply`, anexar `admin_invoke_policy_arn` ao operador, rodar `migrate`, depois `register`.

## 8. Arquivos

**Criados:**
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/aws_lambda/admin_handler.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/interfaces/aws_lambda/test_admin_handler.py`

**Alterados:**
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/Dockerfile`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/infra/terraform/modules/lambda_compute/main.tf`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/infra/terraform/modules/lambda_compute/outputs.tf`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/infra/terraform/environments/production/outputs.tf`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/test_terraform_saas_wiring.py`
- `/mnt/user-data/uploads/agent_multi_IA_context_broker/docs/adr/adr-0019.md`

**Sem mudança:** `environments/production/main.tf`, `modules/network`, `modules/vpc_endpoints`, `modules/database`, `modules/compute`.

## 9. Questões para você decidir

1. **A quem anexar `admin_invoke`?** Usuário IAM, grupo ou permission set do SSO. O Terraform só cria a política. Gerenciar o anexo pede uma variável nova com o nome do principal.
2. **Role dedicada para o admin ou reuso da role da API?** O plano reusa `lambda_execution`, que dá SQS desnecessário ao admin. Uma role própria dá menor privilégio ao custo de ~25 linhas.
3. **CloudTrail data events para `lambda:Invoke`:** necessários para saber quem invocou o admin. Têm custo, e hoje não há trail configurado no repo.
4. **Bug latente fora do escopo, mas real:** `worker_handler.py` e `worker_dlq_handler.py` têm o mesmo padrão de engine em `lru_cache` com `asyncio.run` a cada invocação. Em warm start, as conexões do pool ficam presas a um loop já fechado. A correção seria a mesma linha de `dispose(close=False)`. Aplicar nesta rodada?
5. **`knowledge sync` via admin não funciona:** a imagem Lambda não copia `knowledge/`, enquanto `selfhosted/Dockerfile` copia. **`catalog sync`** deve funcionar pelo NAT. Como o scheduler está desligado no Lambda (`start_background_workers=False`), essa invocação manual passa a ser o único jeito de atualizar o catálogo em produção. Incluir `knowledge/` na imagem?
6. **`migrate` manual ou automático no deploy** (por exemplo, com um recurso `aws_lambda_invocation`)? O plano deixa manual e explícito.
7. **Cold start via `update-function-configuration --description`:** ainda não foi validado numa conta real (a ADR-0019 já avisa). Além disso, o próximo `terraform apply` reverte o `description`. É inofensivo, mas aparece como drift no plan.
8. **Documentação:** ADR nova (adr-0020) ou emenda à ADR-0017/0019?

### Critical Files for Implementation
- /mnt/user-data/uploads/agent_multi_IA_context_broker/infra/terraform/modules/lambda_compute/main.tf
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/aws_lambda/_bootstrap.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/src/auditor/interfaces/cli/main.py
- /mnt/user-data/uploads/agent_multi_IA_context_broker/Dockerfile
- /mnt/user-data/uploads/agent_multi_IA_context_broker/tests/unit/infrastructure/test_terraform_saas_wiring.py
