# Specs — Fase 9: Terraform + Deploy AWS

Formato adaptado: infraestrutura como código verifica-se por `terraform plan`/`apply`
idempotente e por checagens de política, não por `pytest`. Onde um cenário é testável como
dado/quando/então, mantém o formato das fases anteriores; onde é uma decisão de
engenharia com números reais (seção 6), o formato é um checklist a preencher na
implementação, não uma resposta já dada aqui.

---

## 0. Nota de reconciliação — dimensão do embedding

O esboço de schema relacional do plano geral (Parte III, seção 3.7) lista
`knowledge_chunks(..., embedding VECTOR(768), ...)` — um placeholder anterior à decisão de
modelo de embedding tomada de fato em `.cursor/specs/fase6.spec.md`, seção 4
(`sentence-transformers/all-MiniLM-L6-v2`, **384** dimensões, escolhido por rodar CPU-only
sem depender de GPU continuamente ligada — seção 1 abaixo). O RDS/Terraform desta fase
provisiona a extensão `vector` (seção 2.2) sem fixar dimensão nenhuma no nível de
infraestrutura — a coluna `vector(384)` já existe via migration (Fase 6); Terraform só
garante que a extensão está disponível na instância RDS, nunca redefine o schema.

---

> **Superseded pela ADR-0018 (2026-09-15).** A AWS Academy Learner Lab descrita nas seções 1,
> 3, 6 e 9 abaixo **não é mais usada neste projeto** — decisão do usuário, não uma restrição
> técnica nova. `infra/terraform/environments/academy/` foi renomeado para
> `infra/terraform/environments/homolog/`, mantendo a mesma arquitetura EC2 (Ollama em
> instância GPU + API/worker EC2, ADR-0013/ADR-0015) mas apontada para uma conta AWS real —
> sem as restrições do Academy (`create_role` passa a `true`, sem trava de região). O texto
> original abaixo é preservado por valor histórico (mesmo raciocínio das ADRs 0000-0012, ver
> `docs/adr/README.md`) — descreve com precisão o ambiente `environments/academy` **como ele
> existiu**, não o ambiente vigente. Ver ADR-0018 para a decisão completa.

## 1. Restrições do AWS Academy Learner Lab, aplicadas à infraestrutura (plano geral, 1.1)

| Restrição | Consequência no Terraform desta fase |
|---|---|
| Sem `iam:CreateRole` | Todo módulo recebe `create_role: bool` e `existing_role_arn: string \| null` — no ambiente `academy`, `create_role=false` e `existing_role_arn` aponta para a `LabRole` (referenciada via `data "aws_iam_role"`, nunca `resource "aws_iam_role"`). |
| Crédito total US$ 100 | Nenhum recurso fica "sempre ligado" por padrão — instâncias de compute (seção 2.4) e o servidor de SLM (seção 6, se Ollama em EC2) são subidos sob demanda, nunca `count = 1` fixo num ambiente que fica ligado entre sessões. |
| Sessão do lab encerra e derruba recursos | O ciclo `terraform apply` → demo → `terraform destroy` precisa ser **repetível e idempotente** — ver casos de teste da seção 2. Nunca depender de estado manual criado fora do Terraform (um recurso clicado no console AWS não sobrevive à próxima sessão e quebra o próximo `apply`). |
| Regiões `us-east-1`/`us-west-2` apenas | `region` é variável obrigatória sem default fixo num valor fora da lista permitida — validado via `variable "region" { validation { ... } }`. |

---

## 2. Módulos Terraform (plano geral, seção 3.9)

```
infra/terraform/
├── modules/{network,database,queue,compute,secrets}/
└── environments/{academy,production}/
```

### 2.1 `modules/network` — VPC, subnets, security groups

Casos de teste (idempotência — mesmo princípio para todos os módulos abaixo, não repetido
em cada um):
- **Dado** o módulo aplicado uma vez, **quando** `terraform plan` roda de novo sem nenhuma
  mudança de variável, **então** o plano reporta zero mudanças (`0 to add, 0 to change, 0
  to destroy`) — infraestrutura como código só é confiável se for determinística.

### 2.2 `modules/database` — RDS PostgreSQL + pgvector

- Subnet group, parameter group habilitando `shared_preload_libraries` se exigido pela
  versão do RDS PostgreSQL para `vector` (verificar na implementação, versão pode mudar
  esse requisito).
- Migration inicial (Fase 3) já executa `CREATE EXTENSION IF NOT EXISTS vector` — este
  módulo só garante que a instância RDS **suporta** a extensão (versão de engine
  compatível), nunca duplica a criação da extensão via Terraform.

**Caso de teste:**
- **Dado** a instância RDS provisionada, **quando** `alembic upgrade head` roda contra o
  `DATABASE_URL` gerado pelo módulo, **então** todas as migrations (Fases 3–6) aplicam sem
  erro — prova de que o RDS provisionado é, na prática, compatível com o que as fases
  anteriores já validaram contra Postgres local/testcontainers.

### 2.3 `modules/queue` — SQS + DLQ

Espelha exatamente o contrato de `JobQueuePort`/`SqsJobQueue` já implementado e testado com
`moto` na Fase 5 — este módulo só provisiona a fila e a DLQ reais, sem nenhuma lógica nova:
`RedrivePolicy` da fila principal apontando para a DLQ, com `maxReceiveCount` consistente
com o `max_retries` já configurado em `SqsJobQueue` (Fase 5) — **valor duplicado
propositalmente** entre Terraform e código da aplicação; um caso de teste explícito evita
que os dois divirjam silenciosamente:

- **Dado** o `maxReceiveCount` provisionado pelo Terraform e o `max_retries` passado ao
  `SqsJobQueue` na configuração de produção, **quando** comparados, **então** são o mesmo
  número — documentado num único lugar (`infra/terraform/modules/queue/variables.tf`,
  referenciado por comentário na configuração da aplicação) para nunca divergir sem
  ninguém notar.

### 2.4 `modules/compute` — EC2/ECS para API e worker

- API e worker (Fase 5, `AuditWorker`) como serviços separados — o worker não precisa
  responder HTTP, não faz sentido escalar os dois juntos.
- Variável `instance_count`/`desired_count` default baixo (1 de cada) — o Learner Lab
  permite até 9 instâncias/32 vCPU (seção 1.1 do plano geral), mas o TCC não precisa de
  mais que isso para uma demonstração.

> **Superseded para `environments/production` pela ADR-0017 (2026-09-11).** O texto acima
> descreve a arquitetura ORIGINAL desta fase — EC2 para API e worker — e continua valendo
> integralmente para `environments/academy` (onde este TCC de fato roda), preservado aqui
> por valor histórico. A ADR-0017 migra API e worker de `environments/production` para AWS
> Lambda (imagem de contêiner) atrás de um ALB com HTTPS/ACM, seguindo
> `docs/design/implantacao-aws.html` — `modules/compute` passa a provisionar só a instância
> Ollama nesse ambiente (`provision_api=false`, `provision_worker=false`); ver ADR-0017 para
> a decisão completa, o motivo (gap de TLS nunca resolvido pela Fase 9 original) e os
> trade-offs aceitos (cold start, domínio real necessário, `CatalogSyncScheduler` sem
> gatilho automático em produção).

### 2.5 `modules/secrets` — Secrets Manager

Provisiona os ARNs; os **valores** (credenciais reais) nunca entram no Terraform nem em
git (plano geral, seção 3.8) — injetados em tempo de deploy por um passo separado (CI/CD,
seção 7, ou manualmente pelo operador na primeira vez).

> **Superseded para `environments/production` pela ADR-0017.** Continua valendo
> integralmente para `environments/academy`. Em produção, os dois segredos do próprio
> projeto (credenciais do Orion, chave JWT) migram para `modules/parameter_store` (SSM
> SecureString) — `modules/secrets` deixa de ser instanciado em `environments/production`;
> o RDS continua usando Secrets Manager para a senha gerenciada do master user
> (`manage_master_user_password`), decisão independente, da própria feature do RDS.

- `DATABASE_URL` (RDS, módulo 2.2)
- Credenciais do Orion **do cliente**, cifradas em repouso via KMS (segurança, seção 5)
- Chave de assinatura JWT (autenticação, plano geral seção 3.8 — fora do escopo de
  implementação das Fases 1–8, mas a infraestrutura para guardá-la já existe aqui)

---

## 3. Ambientes — `academy` vs `production`

| | `academy` | `production` |
|---|---|---|
| Roles | `create_role=false`, usa `LabRole`/`LabInstanceProfile` existentes (`data`, nunca `resource`) | Cria roles próprias com least privilege (`resource "aws_iam_role"` por serviço) |
| Backend do state | S3 + DynamoDB lock (ambos permitidos no Learner Lab) | Mesmo mecanismo, bucket/tabela separados |
| Ciclo de vida | `apply` antes de cada demo, `destroy` depois — sessão do lab não é permanente | `apply` uma vez, mantido no ar |

### 3.1 Casos de teste

- **Dado** `environments/academy`, **quando** `terraform plan` roda, **então** nenhum
  recurso do tipo `aws_iam_role` aparece no plano de criação — só `data` sources
  referenciando a `LabRole` existente. Este é o teste que teria pego, antes de um `apply`
  falhar em produção real do Academy, a classe inteira de módulo "pronto da internet" que
  o plano geral já identificou como incompatível (seção 1.1).
- **Dado** `environments/production`, **quando** `terraform plan` roda, **então** recursos
  `aws_iam_role` aparecem normalmente — o mesmo código de módulo (`modules/*`) suporta os
  dois ambientes só variando `create_role`, sem duplicar módulos por ambiente.

---

## 4. Backend do state — S3 + DynamoDB lock

- **Dado** dois `terraform apply` disparados concorrentemente (simulando dois membros do
  time ou um CI duplicado), **quando** o segundo tenta adquirir o lock do DynamoDB,
  **então** é bloqueado até o primeiro terminar — nunca dois `apply` concorrentes
  corrompendo o mesmo state.

---

## 5. Segurança (plano geral, seção 3.8) aplicada à infraestrutura provisionada

- TLS: certificado ACM + listener HTTPS no load balancer (módulo `compute`); RDS com
  `sslmode=require` forçado na string de conexão gerada.
- Segredos do broker do cliente cifrados em repouso via KMS (módulo `secrets`) — nunca em
  log (já uma exigência de `structlog`/redaction desde a implementação da API, fora do
  escopo desta fase, mas a chave KMS que viabiliza isso é provisionada aqui).
- `pip-audit` no pipeline de CI (seção 7) — dependência declarada no plano geral (Parte VI,
  6.2) e ainda não configurada em nenhuma fase anterior; **gap conhecido**, ver seção 7.

---

## 6. Decisão final: Bedrock ou Ollama em EC2 (Parte VII do plano geral, "ainda em aberto")

Esta seção documenta o **processo** de decisão, a ser concluído nesta fase com números
reais do orçamento restante do Academy em mãos — não antecipa a resposta, porque a resposta
depende de quanto do crédito de US$ 100 já foi consumido pelas Fases 1–8.

**Checklist a preencher na implementação:**
1. Orçamento restante do Academy (US$) no início desta fase.
2. Custo estimado por auditoria via Bedrock: `tokens médios por entidade no Nível 2 (Fase
   7) × entidades médias por auditoria × preço por 1k tokens do modelo Bedrock escolhido`.
3. Custo estimado via Ollama em EC2: `preço/hora da instância (ex.: g4dn.xlarge, ~US$0,53/h,
   já citado na seção 1.1 do plano geral) × horas efetivamente ligada antes de cada demo`
   — nunca 24/7 (orçamento não comporta, seção 1).
4. Comparar (2) vs (3) dentro do orçamento restante (1); a opção mais barata para o volume
   de demonstrações esperado (banca + ensaios) vence.
5. Se Ollama em EC2 vencer: a instância **precisa** de um script de start/stop explícito
   (`infra/terraform/environments/academy/scripts/`) — nunca deixada ligada por padrão,
   dado o limite de crédito.

**Caso de teste (verificável independente do resultado da decisão):**
- **Dado** a decisão tomada (Bedrock ou Ollama-EC2), **quando** `container.py`
  (`get_semantic_analyzer`, análogo aos factories já existentes desde a Fase 4) é
  configurado para o ambiente `production`/`academy`, **então** troca de adapter é só
  configuração (`Settings`) — nenhuma mudança em `RunAuditUseCase` nem em
  `SemanticAnalyzerPort` (Fase 7), prova viva de que "duas implementações desde o início"
  (Fase 7, seção 6) cumpriu o propósito de tornar essa troca barata.

---

## 7. CI/CD — gap conhecido da Fase 0, resolvido aqui no que for necessário para deploy

A Fase 0 do plano geral (fundação do repositório: `ruff`, `mypy --strict`, pre-commit, CI
via GitHub Actions) nunca foi executada neste repositório — confirmado ao levantar o que
falta antes desta fase. Esta fase **não** assume que ela existe; o mínimo necessário para
deploy repetível é adicionado aqui, mesmo que a cobertura completa de lint/type-check fique
como débito registrado (não bloqueia esta fase, mas deve constar na monografia como
limitação conhecida do processo):

- Workflow de GitHub Actions rodando `terraform plan` em PRs que tocam `infra/terraform/`
  (revisão do plano antes de aplicar) e `terraform apply` manual/aprovado para o ambiente
  `academy` antes de cada demonstração.
- `pip-audit` (seção 5) incluído neste mesmo workflow, ainda que o restante da Fase 0
  (lint/type-check do código Python) continue pendente.

---

## 8. Fora de escopo desta fase

- Frontend em produção além do mínimo (build estático do Angular, Fase 8, hospedado em
  S3 + CloudFront ou servido pelo mesmo compute da API) — otimização de CDN/cache não é
  foco do TCC.
- Autoscaling, multi-região, blue/green deploy — além do escopo de um protótipo de TCC;
  registrado como trabalho futuro na monografia (Fase 10), não implementado aqui.
- Cobertura completa da Fase 0 (lint/type-check em 100% do código já escrito nas Fases
  1–8) — gap conhecido, ver seção 7.

---

## 9. Definição de pronto da Fase 9

- `terraform apply` no ambiente `academy` funciona contra o Learner Lab real, sem nenhum
  erro de permissão (`iam:CreateRole` ou similar) — prova de que `create_role=false` e as
  referências a `LabRole` (seção 3) realmente evitam a classe de erro que módulos prontos
  da internet cometem (plano geral, seção 1.1).
- Ciclo `apply` → smoke test (Fase 4's E2E, agora contra infraestrutura real) → `destroy`
  é repetível sem intervenção manual — testado pelo menos duas vezes seguidas antes de
  confiar nele para a banca.
- Decisão Bedrock vs. Ollama-EC2 (seção 6) tomada e documentada com números reais, não um
  placeholder.
- Nenhum segredo real em git — `.env.example` sem valores reais, `terraform.tfvars` com
  segredos no `.gitignore`, revisado manualmente antes do primeiro commit desta fase.
- `pip-audit` limpo (ou com exceções documentadas e justificadas) no workflow de CI da
  seção 7.
