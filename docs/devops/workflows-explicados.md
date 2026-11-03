# Pipeline explicada: cada arquivo, o fluxo depois do push e o `terraform plan`

Complementa `docs/devops/pipeline-e-ambientes.md` (configuração inicial) e `docs/adr/adr-0021.md` (por que a pipeline é assim). Segue o Manual de Gestão de Código e Entrega v1.3.

## 1. Mapa rápido

```
.github/
  workflows/
    ci-backend.yml          testes Python (unitários, integração, golden)
    ci-frontend.yml         testes e build do Angular
    ci-images.yml           confere se as 3 imagens Docker compilam
    ci-infra.yml            terraform fmt, validate e plan (informativo)
    security.yml            pip-audit, npm audit, gitleaks
    deploy-dev.yml          entrega no DEV (manual, escolhe a branch)
    deploy-homologacao.yml  entrega na HOMOLOGAÇÃO (tag vX.Y.Z-rc.N)
    deploy-producao.yml     entrega na PRODUÇÃO (tag vX.Y.Z)
    rollback-producao.yml   volta a produção para uma versão anterior
    infra-apply.yml         terraform plan/apply manual por ambiente
  actions/
    deploy-lambda/          troca a imagem das Lambdas (com migrações)
    deploy-frontend/        publica o frontend no S3 e invalida o CloudFront
  dependabot.yml            PRs semanais de atualização de dependências
scripts/ci/
  smoke.sh                  teste de fumaça (/health e frontend)
  ssm_run.sh                roda comando na EC2 do DEV via SSM
  set_api_url.sh            troca a URL da API dentro do build do frontend
  acceptance_dkrt.py        3 cenários DKRT na homologação
infra/terraform/
  bootstrap/                state remoto, bucket de artefatos, OIDC e papéis IAM
  environments/{dev,homolog,production}/
  modules/
```

Duas ideias organizam tudo:

- **Os `ci-*` e o `security` são "portões" reutilizáveis.** Rodam sozinhos em PR e são chamados (`workflow_call`) pelos workflows de deploy, que só avançam se eles passarem.
- **Construir uma vez, promover o mesmo.** A imagem Lambda e o frontend são construídos na homologação. A produção copia os mesmos bits, sem reconstruir.

## 2. O que acontece depois do push (por situação)

| O que você faz | O que roda | Resultado |
|---|---|---|
| `git push` de uma branch de trabalho (feature, fix) | **Nada.** Os CI não disparam em push de branch comum | Abra o PR |
| Abrir/atualizar um **PR para a `main`** | `ci-backend`, `ci-frontend`, `ci-images`, `ci-infra`, `security` (cada um só se o PR tocou as pastas dele) | Checks verdes/vermelhos no PR. O Tech Lead só faz merge com tudo verde |
| PR que mexe em `infra/terraform/**` | `ci-infra`: `fmt` e `validate` bloqueiam; em seguida o `plan` dos 3 ambientes é publicado no resumo do job | Revisar o plano antes do merge. O plan não bloqueia |
| **Merge na `main`** | **Nada é implantado.** (Não há deploy automático na `main`) | A entrega é sempre por ação explícita (abaixo) |
| Dev quer testar no DEV: **Actions → Deploy DEV → Run workflow**, escolhendo a branch | `ci-backend` + `ci-frontend` + `security` → build da imagem → migrações → troca do contêiner → build e publicação do frontend → fumaça | DEV com a branch escolhida. O Q.A testa (1º ciclo) |
| Tech Lead cria `release/X.Y.Z` e dá push | `ci-backend`, `ci-frontend`, `ci-images`, `ci-infra`, `security` (gatilho `push` em `release/**`) | Confirma que a release está saudável |
| Tech Lead publica a tag **`vX.Y.Z-rc.N`** em commit da `release/X.Y.Z` | `deploy-homologacao` (detalhes na seção 3.7) | HOMOLOGAÇÃO atualizada. O Q.A testa (2º ciclo) |
| Q.A aprovou: Tech Lead faz **merge da `release/X.Y.Z` na `main`** e publica a tag **`vX.Y.Z`** na `main` | `deploy-producao` (seção 3.8). Pausa pedindo **aprovação manual** | PRODUÇÃO atualizada com a mesma imagem/frontend da `-rc`; release criada no GitHub |
| Deu problema em produção: **Actions → Rollback PRODUÇÃO → Run workflow** com a versão anterior | `rollback-producao` (seção 3.9) | Produção volta para a versão informada |
| Precisa mudar infraestrutura: **Actions → Infra (Terraform plan/apply)** | `infra-apply` (seção 3.10) | Plano mostrado; apply só se pedido e aprovado |
| Segunda-feira de manhã (cron) | `security` (07:00 UTC) e `golden` do SLM (06:00 UTC, em `ci-backend`) | Alerta de vulnerabilidade nova e regressão de prompt, sem commit |
| Toda semana | Dependabot abre PRs | Revisar e fazer merge |

Linha do tempo de uma versão:

```
feature ──PR──► main ──► (DEV manual p/ testar) ──► release/X.Y.Z ──tag vX.Y.Z-rc.N──► HOMOLOG
                                                                                          │ Q.A aprova
                       main ◄──────merge release/X.Y.Z────────────────────────────────────┘
                        └──tag vX.Y.Z──► aprovação manual ──► PRODUÇÃO (mesma imagem da rc)
```

Observações: `ci-backend`, `ci-frontend`, `ci-images` e `security` filtram PRs por `branches: [main]`; um PR para outra branch não os aciona (o `ci-infra` roda em qualquer PR que toque o Terraform). Nos pushes em `release/**`, o `ci-infra` só roda se a mudança tocou `infra/terraform/**`. Se a equipe usar `develop` como destino de PR, adicione `develop` nesses filtros.

## 3. Cada arquivo

### 3.1 `ci-backend.yml`

- **Gatilhos:** PR para `main` que toque `src/`, `tests/`, `migrations/`, `alembic.ini`, `requirements.txt`, `pyproject.toml`; push em `release/**`; cron semanal; `workflow_call` (usado pelos deploys); `workflow_dispatch`.
- **Job `unit`:** instala dependências (torch em versão CPU, por tamanho), roda `ruff` e `mypy` **só nos arquivos Python que mudaram** contra a `main` (o débito antigo não bloqueia, mas ninguém piora o que tocar), roda `pytest tests/unit` com cobertura e guarda o `coverage.xml` por 14 dias.
- **Job `integration`:** sobe PostgreSQL (pgvector), MongoDB e Orion como serviços; confere que existe **uma única head do Alembic**; aplica as migrações num banco vazio; roda `pytest -m integration`.
- **Job `golden`:** só no cron semanal ou manual. Instala o Ollama, baixa `qwen2.5:3b-instruct` e roda os testes golden. Não bloqueia (`continue-on-error`), porque é pesado e instável.

### 3.2 `ci-frontend.yml`

PR em `frontend/**`, push em `release/**`, `workflow_call`. Um job: `npm ci`, `ng test` em Chrome headless e `ng build` de produção.

### 3.3 `ci-images.yml`

Compila (sem publicar) as três imagens: Lambda (`Dockerfile` da raiz), API self-hosted e frontend self-hosted. Pega Dockerfile quebrado antes do deploy.

### 3.4 `ci-infra.yml`

- **`fmt`:** `terraform fmt -check -recursive`. Bloqueia.
- **`validate`:** `init -backend=false` + `validate` nos 4 stacks (bootstrap, dev, homolog, production). Bloqueia.
- **`plan`:** só em PR do próprio repositório e só se a variável `AWS_PLAN_ROLE_ARN` existir. Assume o papel somente-leitura por OIDC, faz `init` com o state remoto e roda `terraform plan` dos 3 ambientes, publicando as últimas 60 linhas no resumo do job. É informativo (`continue-on-error`); nunca aplica.
- Os valores do ambiente (domínios, zona Route53, URL do Orion) vêm da variável de repositório `TFVARS_DEV`, `TFVARS_HOMOLOG` ou `TFVARS_PRODUCTION`.

### 3.5 `security.yml`

`pip-audit` (requirements.txt), `npm audit` (só produção, críticas e altas) e `gitleaks` (varredura de segredos no histórico). Roda em PR, push em `release/**`, cron semanal e antes de cada deploy.

### 3.6 `deploy-dev.yml`

- **Gatilho:** só `workflow_dispatch`. A branch escolhida no botão é a que será implantada. A fila (`concurrency: deploy-dev`) impede dois deploys ao mesmo tempo.
- **Etapas:** CI (backend, frontend, segurança) → login na AWS por OIDC (Environment `dev`) → build da imagem `selfhosted` com tag `dev-<sha7>` e push no ECR → acha a EC2 `auditor-dev-api` → migrações Alembic e troca do contêiner via SSM (`auditor-deploy migrate|start`) → build do frontend, troca da URL da API e `s3 sync` → fumaça.
- **Importante:** o artefato do DEV nunca é promovido para homologação.

### 3.7 `deploy-homologacao.yml`

- **Gatilho:** push da tag `vX.Y.Z-rc.N`.
- **`validar-tag`:** a tag precisa apontar para um commit que esteja na `release/X.Y.Z` **e** a release precisa conter a `main` atual (senão: traga a main e publique outra `-rc`).
- **Portões:** `ci-backend`, `ci-frontend`, `ci-infra`, `ci-images`, `security`.
- **`build`** (Environment `homologacao`): constrói a imagem Lambda (com `provenance` e `sbom` desligados, porque o Lambda não aceita o formato) e dá push com a tag da `-rc`; constrói o frontend e guarda o `dist.tgz` no bucket de artefatos em `frontend/<tag>/`.
- **`deploy`:** ação `deploy-lambda` (migra, depois troca as funções) e `deploy-frontend`.
- **`verificar`:** `smoke.sh` e, se `ORION_URL` estiver definida, os 3 cenários DKRT (`acceptance_dkrt.py`). Sem `ORION_URL` o passo é pulado com aviso: o Q.A precisa rodá-los à mão.

### 3.8 `deploy-producao.yml`

- **Gatilho:** push da tag `vX.Y.Z`.
- **`validar-tag`:** a tag precisa estar na `main` e deve existir uma `vX.Y.Z-rc.*`. O **conteúdo** (árvore do git) da tag precisa ser idêntico ao da `-rc` mais recente. Se alguém mudou algo depois de homologar, falha e pede nova `-rc`.
- **Portões:** `ci-backend`, `ci-frontend`, `ci-infra`, `security`.
- **`promover`** (Environment `producao` → **pausa para aprovação manual**): copia a imagem do ECR de homologação para o de produção (`docker pull/tag/push`) e confere que o **digest é o mesmo**; copia o build do frontend para `frontend/vX.Y.Z/` (é daí que o rollback parte).
- **`deploy`:** `deploy-lambda`, `deploy-frontend`, fumaça.
- **`release-notes`:** cria a release no GitHub com notas geradas.

### 3.9 `rollback-producao.yml`

Entrada: `versao` (ex.: `v1.2.0`). Valida o formato, confere que imagem e frontend dessa versão existem, e aplica `deploy-lambda` **sem migrações** (`run-migrations: false`) e `deploy-frontend` dela, seguido de fumaça. Exige a aprovação do Environment `producao`. Se uma migração destrutiva foi aplicada, voltar o código não desfaz o banco: restaure por snapshot do RDS.

### 3.10 `infra-apply.yml`

Entradas: `ambiente` (dev, homolog, production) e `acao` (plan ou apply). Job `plan`: `init` com o state do ambiente, `plan` com o tfvars da variável de repositório, resumo no job e, se for apply, guarda o `tfplan`. Job `apply`: baixa **o mesmo plano** e aplica. Os dois jobs usam o Environment `infra-<ambiente>`; em produção, com revisores obrigatórios, aprova-se o plano e depois o apply.

### 3.11 Ações compostas

- **`deploy-lambda`:** atualiza a função `admin` com a imagem nova → invoca `{"argv":["migrate"]}` e exige `exit_code == 0` → só então atualiza `api`, `worker` e `worker-dlq` e espera ficarem prontas. Migração antes do código novo receber tráfego.
- **`deploy-frontend`:** baixa o `dist.tgz`, troca `http://localhost:8000` pela URL da API do ambiente (`set_api_url.sh`), sincroniza com o bucket (`index.html` sem cache, o resto imutável) e invalida o CloudFront.

### 3.12 Scripts de apoio e Dependabot

`smoke.sh` tenta `/health/live`, `/health/ready` e o frontend por até 5 minutos. `ssm_run.sh` roda um comando na EC2 do DEV e falha se ele falhar. `set_api_url.sh` falha se não achar a URL padrão no build (a premissa deixou de valer). `acceptance_dkrt.py` usa só a biblioteca padrão: grava 3 entidades no Orion, dispara uma auditoria e confere que a correta fica `conformant` e as outras duas não. O Dependabot cobre pip, npm, GitHub Actions e Terraform (produção).

## 4. Como rodar o `terraform plan`

Pré-requisito comum: o **bootstrap** já foi aplicado (existem o bucket de state, a tabela de lock e os papéis). Sem ele, não há onde guardar o state.

### Opção A: pelo GitHub (recomendada, não precisa de credencial local)

1. **Actions → Infra (Terraform plan/apply) → Run workflow**.
2. Escolha o `ambiente` (dev, homolog ou production) e `acao = plan`.
3. Em `production`, aprove o Environment `infra-production`.
4. Abra o job: o plano está no **resumo** (final do log do passo `terraform plan`).

Nada é alterado na AWS. Para aplicar, rode de novo com `acao = apply`: ele refaz o plano, pede a aprovação e aplica o plano salvo.

### Opção B: automática no PR

Qualquer PR que toque `infra/terraform/**` roda o `ci-infra`. O plano dos 3 ambientes aparece no resumo do job `plan`, se a variável de repositório `AWS_PLAN_ROLE_ARN` estiver configurada. PR de fork não recebe esse plano.

### Opção C: na sua máquina

Precisa do Terraform (>= 1.5; o CI usa 1.9.8) e do AWS CLI, com credenciais que leiam o state e os recursos (ex.: `aws configure sso` e `aws sts get-caller-identity` para conferir).

```powershell
# Ex.: homologação (troque por dev ou production)
cd infra\terraform\environments\homolog

# 1) valores do ambiente (o arquivo é ignorado pelo git)
Copy-Item terraform.tfvars.example terraform.tfvars
# edite: api_domain_name, frontend_domain_name, route53_zone_id, fiware_broker_url

# 2) init apontando para o state remoto (ID da conta = aws sts get-caller-identity)
terraform init `
  -backend-config="bucket=auditor-tfstate-<ID_DA_CONTA>" `
  -backend-config="key=homolog/terraform.tfstate" `
  -backend-config="region=us-east-1" `
  -backend-config="dynamodb_table=auditor-tflock"

# 3) plano
terraform plan -out=tfplan
```

A `key` do state é `<ambiente>/terraform.tfstate`, com `dev`, `homolog` ou `production`. Os nomes do bucket e da tabela são as saídas `tf_state_bucket` e `tf_state_lock_table` do bootstrap. Para só conferir sintaxe, sem AWS: `terraform init -backend=false` e `terraform validate`.

Se o `plan` pedir variável sem valor, ela falta no `terraform.tfvars` (no GitHub: na variável `TFVARS_<AMBIENTE>`). No `dev`, defina `ssh_cidr_blocks` apenas se quiser SSH; sem ele a porta 22 fica fechada (o acesso é por Session Manager).

### Primeiro provisionamento de homologação/produção

As Lambdas nascem apontando para a tag `bootstrap` no ECR, que ainda não existe. Por isso a primeira vez tem uma ordem:

1. `terraform apply -target=module.stack.module.lambda_compute.aws_ecr_repository.this` (cria só o repositório).
2. Construa e publique qualquer imagem Lambda como `<repositório>:bootstrap` (ex.: `docker build -t <url_ecr>:bootstrap .` e `docker push`, após `aws ecr get-login-password | docker login`).
3. `terraform apply` completo (ou `infra-apply` com `acao = apply`).
4. Faça o deploy real: tag `-rc` (homologação) ou o fluxo da produção. O Terraform não troca mais a imagem depois (`ignore_changes`).

Para o `dev` (EC2), não há essa etapa: faça `apply` e depois rode o **Deploy DEV**.

## 5. Variáveis e Environments que os workflows leem

- **Repositório (variáveis):** `AWS_REGION`, `TF_STATE_BUCKET`, `TF_STATE_LOCK_TABLE`, `ARTIFACTS_BUCKET`, `AWS_PLAN_ROLE_ARN`, `TFVARS_DEV`, `TFVARS_HOMOLOG`, `TFVARS_PRODUCTION`.
- **`infra-dev`, `infra-homolog`, `infra-production`:** `AWS_TERRAFORM_ROLE_ARN`.
- **`dev`, `homologacao`, `producao`:** `AWS_DEPLOY_ROLE_ARN`, `NAME_PREFIX`, `API_URL`, `FRONTEND_URL`, `FRONTEND_DOMAIN` (homolog e produção). Em `producao`, também `HOMOLOG_NAME_PREFIX`.
- **Opcionais em `homologacao`:** `ORION_URL`, `FIWARE_SERVICE`, `FIWARE_SERVICE_PATH` e os segredos `ACCEPTANCE_EMAIL` e `ACCEPTANCE_PASSWORD`.
- **Proteções:** `producao` e `infra-production` com revisores obrigatórios e "Prevent self-review"; branch protection na `main` exigindo os checks `ci-backend`, `ci-frontend`, `ci-infra` e `security`.
