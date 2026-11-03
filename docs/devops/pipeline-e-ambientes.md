# Pipeline e ambientes (dev, homologação, produção)

Decisão: `docs/adr/adr-0021.md`. Processo: Manual de Gestão de Código e Entrega (v1.3), seção 4.

## Visão geral

| Ambiente | Prefixo | Arquitetura | Gatilho | Aprovação |
|---|---|---|---|---|
| DEV | `auditor-dev` | EC2 (contêiner `selfhosted`) + RDS + S3 website | `Deploy DEV` (Run workflow, escolhe a branch) | Environment `dev` (opcional) |
| HOMOLOGAÇÃO | `auditor-homolog` | Lambda + ALB + CloudFront/S3 + RDS | tag `vX.Y.Z-rc.N` em `release/X.Y.Z` | Environment `homologacao` |
| PRODUÇÃO | `auditor-prod` | Lambda + ALB + CloudFront/S3 + RDS Multi-AZ | tag `vX.Y.Z` na `main` | Environment `producao` (revisores obrigatórios) |

Fluxo: PR → CI (por pasta) → merge → DEV (Q.A, 1º ciclo) → `release/X.Y.Z` + tag `-rc` →
HOMOLOGAÇÃO (Q.A, 2º ciclo) → merge na `main` + tag `vX.Y.Z` → PRODUÇÃO (mesma imagem e
mesmo frontend, promovidos). Rollback: workflow `Rollback PRODUÇÃO` com a versão anterior.

## Workflows

- `ci-backend`, `ci-frontend`, `ci-infra`, `ci-images`, `security`: rodam em PR por pasta e são chamados pelos deploys.
- `deploy-dev`, `deploy-homologacao`, `deploy-producao`, `rollback-producao`: entrega.
- `infra-apply`: Terraform `plan`/`apply` manual por ambiente.
- Ações compostas: `.github/actions/deploy-lambda` (migra e troca as funções) e `deploy-frontend`.

## Configuração única (ordem)

1. **Bootstrap** (uma vez, com credenciais de administrador): `cd infra/terraform/bootstrap`,
   copiar `terraform.tfvars.example`, `terraform init && terraform apply`. Se a conta já tem o
   provedor OIDC do GitHub, `create_oidc_provider = false`. Anotar as saídas.
2. **Variáveis de repositório** (Settings → Secrets and variables → Actions → Variables):
   `AWS_REGION`, `TF_STATE_BUCKET`, `TF_STATE_LOCK_TABLE`, `ARTIFACTS_BUCKET`, `AWS_PLAN_ROLE_ARN`,
   `TFVARS_DEV`, `TFVARS_HOMOLOG`, `TFVARS_PRODUCTION` (conteúdo no formato de cada
   `terraform.tfvars.example`; só valores não secretos).
3. **GitHub Environments** e suas variáveis:
   - `infra-dev`, `infra-homolog`, `infra-production`: variável `AWS_TERRAFORM_ROLE_ARN`
     (`infra-production` com revisores obrigatórios; ela aprova o plan e depois o apply).
   - `dev`, `homologacao`, `producao`: `AWS_DEPLOY_ROLE_ARN`, `NAME_PREFIX`, `API_URL`,
     `FRONTEND_URL`, `FRONTEND_DOMAIN` (homolog/prod), e em `producao` também `HOMOLOG_NAME_PREFIX`.
     Opcional em `homologacao`: `ORION_URL`, `FIWARE_SERVICE`, `FIWARE_SERVICE_PATH` e os
     segredos `ACCEPTANCE_EMAIL`/`ACCEPTANCE_PASSWORD` para os 3 cenários DKRT.
   - `producao`: revisores obrigatórios e "Prevent self-review".
4. **Branch protection** (`main`, `develop`): exigir os checks `ci-backend`, `ci-frontend`,
   `ci-infra` e `security`.
5. **Primeiro provisionamento** de cada ambiente: `infra-apply` (plan, depois apply). Nos
   ambientes Lambda a primeira criação usa a imagem `bootstrap`; em seguida rodar o deploy do
   ambiente (DEV manual, HOMOLOG por tag `-rc`).

## Operação

- **Ollama (SLM)** não fica ligado por padrão: `infra/terraform/scripts/start_ollama.sh` e
  `stop_ollama.sh`.
- **Migração destrutiva em produção:** o rollback do código não desfaz o banco; restaurar por
  snapshot do RDS.
- **Branch `main` não deve receber commit direto**: merge só por PR (manual, seção 3).

## Pontos de atenção

- `terraform validate/plan/apply` não foram executados na autoria; o primeiro `plan` real pode
  exigir pequenos ajustes (versões de provedor, nomes de recurso).
- O papel `plan` (PR) é somente leitura (ReadOnlyAccess + state); não vê segredos além do
  que o `ReadOnlyAccess` permite, incluindo parâmetros SSM; revise se isso é aceitável.
- Os cenários DKRT na homologação exigem um Orion acessível pelo runner; sem `ORION_URL`
  o workflow avisa e o Q.A deve rodá-los à mão.
