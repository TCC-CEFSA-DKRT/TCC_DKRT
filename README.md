# FIWARE Conformance Auditor

Audita entidades do **FIWARE Orion Context Broker** (NGSI-v2) contra **Smart Data Models**,
combinando validação estrutural determinística (**Nível 1** — JSON Schema) com diagnóstico
semântico via SLM local + RAG (**Nível 2** — detecta o que o Nível 1 não alcança, ex.:
`temp` vs `temperature`).

> Projeto de TCC. Arquitetura hexagonal (ports & adapters) — ver `docs/plano_refatoracao_v3.md`
> (plano mestre) e `.cursor/specs/fase1.spec.md` a `fase10.spec.md` (specs por fase, fonte de
> verdade sobre comportamento). Decisões arquiteturais: `docs/adr/` (ver seu próprio índice
> para o que é histórico e o que é vigente). Documentação de uma iteração anterior do projeto
> (um sistema multiagente, descartado) foi movida para `docs/legacy/` — nada lá descreve o
> sistema atual.

## Arquitetura, em uma imagem

```
REST (FastAPI) · CLI (Typer)              ← entrada
        ↓
RunAuditUseCase, GetAuditReportUseCase...  ← application (orquestra)
        ↓
StructuralValidator (Nível 1, puro)        ← domain (zero I/O, zero dependência externa)
        ↓
OrionAdapter · SmartDataModelsAdapter ·    ← infrastructure (adapters)
OllamaAnalyzer/BedrockAnalyzer (Nível 2) ·
PostgresAuditRepository · PgVectorRetriever
```

`domain/` nunca importa `fastapi`/`sqlalchemy`/`httpx`/`boto3` — verificado automaticamente
(`tests/unit/domain/test_architecture.py`).

## Requisitos

- Python **3.11+**
- Docker + Docker Compose (infraestrutura local: Orion, Mongo, Postgres/pgvector)
- [Ollama](https://ollama.com/) (opcional — sem ele, o Nível 2 fica indisponível de forma
  graciosa; auditorias continuam rodando só com o Nível 1)
- Node 20+ / npm (só para o frontend Angular, `frontend/`)

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env
```

## 1. Infraestrutura local (Orion, Mongo, Postgres)

```bash
docker compose up -d
docker compose ps      # aguarde orion/mongo/postgres "healthy"
```

`docker-compose.yml` sobe **só a infraestrutura** (Orion 1026, Postgres/pgvector 5433) — a
aplicação (API/worker) não roda em container nenhum hoje, é processo Python direto (passo 3).

## 2. Migrations

```bash
alembic upgrade head
```

## 3. Rodando a aplicação

```bash
uvicorn auditor.interfaces.rest.app:app --reload --port 8000
```

Um único processo sobe API + worker (`AuditWorker`) + sincronizador de catálogo
(`CatalogSyncScheduler`) juntos, como tasks em background (`interfaces/rest/app.py`) — não
precisa de um segundo terminal para o worker em desenvolvimento. Health check:
`curl http://localhost:8000/health`.

### SLM (Nível 2) — Ollama local

Ollama **não sobe com `docker compose up -d`** — o compose acima só gerencia infraestrutura de
dados (Orion, Mongo, Postgres/pgvector), nunca o SLM. Ollama roda nativo na máquina, uma única
vez, ficando de pé em background enquanto você usa o projeto (não é um passo a repetir a cada
`uvicorn` que você reinicia):

```bash
ollama serve                       # deixe rodando num terminal/background
ollama pull qwen2.5:7b-instruct    # só na primeira vez
```

`.env` já aponta para `http://localhost:11434` / `qwen2.5:7b-instruct` por padrão
(`OLLAMA_BASE_URL`, `OLLAMA_MODEL`). Sem Ollama rodando, o Nível 2 não derruba a auditoria —
`SemanticAnalyzerPort` captura a falha de conexão e marca a análise como indisponível
(`analysis_unavailable`), sem alucinar um resultado.

## Instalação self-hosted (ambiente do produtor)

Ver ADR-0019 (`docs/adr/adr-0019.md`) para o raciocínio completo. Os arquivos ficam em
`selfhosted/` (separados do `Dockerfile`/`docker-compose.yml` da raiz, que são do modo
SaaS/dev — ver "O que é cada arquivo Docker" abaixo). Para o produtor instalar a ferramenta na
própria infraestrutura (SLM incluso, sem depender de nada externo):

```bash
cd selfhosted
docker compose up -d --build
```

Sobe Orion+Mongo, Postgres/pgvector, Ollama (CPU-only por padrão — usa GPU sozinho se a
máquina tiver uma) e a aplicação — migrations, sincronização do RAG e download do modelo do
Ollama rodam automaticamente antes da API aceitar tráfego, sem nenhum comando manual. Se o
produtor já tem um Orion próprio, remova os serviços `mongo`/`orion` de
`selfhosted/docker-compose.yml` e aponte `FIWARE_BROKER_URL` (nos serviços `migrate` e `app`)
para o broker existente.

> Ainda não testado com `docker compose up` real — validado só como Compose/YAML
> sintaticamente corretos. Rode localmente e reporte o que falhar antes de considerar pronto
> para instalação em produção de um cliente.

A chave de cifragem (`BROKER_API_KEY_ENCRYPTION_KEYS`) é gerada sozinha, na primeira subida, no
volume nomeado `auditor-secrets` — nenhum passo manual. Esse volume precisa entrar no backup
junto com `auditor-postgres-data`: perder só o primeiro torna ilegíveis as `broker_api_key`
cifradas gravadas no segundo. `docker compose down -v` apaga os dois.

### O que é cada arquivo Docker

| Arquivo | Modo | O que sobe |
|---|---|---|
| `docker-compose.yml` (raiz) | Dev local | Só infraestrutura (Orion, Mongo, Postgres) — a aplicação roda como processo Python direto (`uvicorn`, passo 3 acima) |
| `Dockerfile` (raiz) | Homologação e produção | Handler Lambda (ADR-0017) — nunca roda com `docker run`/`docker compose`, só via pipeline + ECR |
| `selfhosted/docker-compose.yml` | Self-hosted | Stack completa (infra + app + SLM) para o produtor instalar na própria infraestrutura |
| `selfhosted/Dockerfile` | Self-hosted | Mesmo código do `Dockerfile` da raiz, mas roda `uvicorn` normal em vez de handler Lambda |

## CLI

```bash
audit run --tenant openiot --entity-type Streetlight
audit run --tenant openiot --entity-type Streetlight --entity-id urn:ngsi-ld:Streetlight:001
audit status --run-id <uuid>
audit catalog sync     # popula o catálogo de Smart Data Models (necessário antes do 1º uso)
```

`--tenant`/`--service-path` são opcionais — caem para `FIWARE_SERVICE`/`FIWARE_SERVICE_PATH`
de `.env` quando omitidos.

## Frontend (Angular) — Fase 8

```bash
cd frontend
npm install
npm start          # ng serve — http://localhost:4200, contra a API em http://localhost:8000
npm test           # Karma/Jasmine (ChromeHeadless)
npm run build       # build de produção em dist/frontend
```

A API precisa estar rodando (passo 3) com CORS liberado para `http://localhost:4200`
(`CORS_ALLOWED_ORIGINS`, já é o padrão de `.env.example`). Cinco telas: Dashboard, Audit Runs,
Report Detail, Natural Language, Catalog. Tenant fixo em tempo de build
(`frontend/src/app/core/api-config.ts`) — não há tela de login nesta fase.

## Testes

```bash
pytest tests/unit -q                          # domínio + aplicação + infra, sem I/O externo
pytest tests/ -v -m integration                # exige Postgres/Orion reais (docker compose up)
pytest tests/ -v -m golden                     # exige Ollama real — detecta regressão de prompt
```

Markers definidos em `pyproject.toml` (`[tool.pytest.ini_options]`). O CI
(`.github/workflows/ci-backend.yml`, ver `docs/devops/pipeline-e-ambientes.md`) roda a suíte em
todo PR (unitários, `integration` com Postgres/Orion em serviço e `golden` com Ollama).

## Experimento (Fase 10 — métricas do TCC)

```bash
python scripts/run_experiment.py \
    --dataset-dir dataset/experiment \
    --broker-url http://localhost:1026 \
    --api-base-url http://localhost:8000 \
    --tenant experiment
```

Requer o mesmo ambiente do passo 1-3 de pé, com um SLM real acessível — nunca roda contra
mocks. Ver `.cursor/specs/fase10.spec.md` e `dataset/experiment/README.md` (formato do
dataset — curadoria humana, não gerada por ferramenta).

## Infraestrutura AWS (Terraform) e pipeline — ADR-0021

Três ambientes na AWS, numa única conta, com prefixo por ambiente (detalhes e passo a passo em
`docs/devops/pipeline-e-ambientes.md`):

| Ambiente | Pasta Terraform | Arquitetura |
|---|---|---|
| dev | `infra/terraform/environments/dev` | EC2 (contêiner `selfhosted`) + RDS + S3 website |
| homologação | `infra/terraform/environments/homolog` | Lambda + ALB + CloudFront/S3 + RDS (`modules/stack_lambda`) |
| produção | `infra/terraform/environments/production` | mesma stack Lambda, Multi-AZ |

`infra/terraform/bootstrap` cria o state remoto, o bucket de artefatos, o provedor OIDC do GitHub
e os papéis IAM (aplicado uma vez, à mão). Os workflows entram na AWS por OIDC, sem chaves de
acesso. Pipeline (manual de gestão de código v1.3): DEV por `workflow_dispatch` da branch
escolhida; HOMOLOGAÇÃO pela tag `vX.Y.Z-rc.N` em `release/X.Y.Z`; PRODUÇÃO pela tag `vX.Y.Z` na
`main`, com aprovação manual, promovendo a mesma imagem e o mesmo frontend já homologados.

**Estado real:** o Terraform foi formatado (`fmt`) e conferido estruturalmente, mas **nenhum
`validate`/`plan`/`apply` foi executado contra uma conta AWS real**.

## Servidor MCP (ADR-0016)

**Decisão aceita, ainda não implementada** nesta arquitetura — `docs/adr/adr-0016.md` registra
expor a auditoria como ferramenta MCP para clientes de IA, mas não existe hoje um
`interfaces/mcp/` correspondente (a versão antiga, `services/mcp_server.py`, pertencia ao
sistema multiagente descartado e está em `docs/legacy/`, não é reaproveitável como está).

## Débito conhecido (documentado, não bloqueante para o TCC)

- Lint/type-check completos (`mypy`/`ruff` em 100% do código) fora de escopo — só código novo
  é obrigado a não introduzir violação nova.
- `docs/plano_refatoracao_v3.md` (Parte I, 1.1) ainda descreve as restrições da AWS Academy
  Learner Lab como vigentes — não atualizado pela ADR-0018 (reescrita grande, follow-up
  separado); `.cursor/specs/fase9.spec.md` já tem uma nota apontando para a ADR-0018.
- Servidor MCP (ADR-0016) aceito mas não implementado (ver seção acima).

## Estrutura do projeto

```
src/auditor/
├── domain/            # entidades, value objects, ports, StructuralValidator — zero I/O
├── application/        # use cases (RunAuditUseCase, SyncCatalogUseCase, ...)
├── infrastructure/      # adapters: context_broker, schema_catalog, llm, rag, persistence, queue, config
├── interfaces/          # rest (FastAPI), cli (Typer), worker, aws_lambda
experiment/               # scripts/run_experiment.py + auditor/experiment (Fase 10)
tests/{unit,integration,golden}/
infra/terraform/{modules,environments}/
frontend/                # Angular (Fase 8)
docs/
├── plano_refatoracao_v3.md   # plano mestre — fonte de verdade sobre decisões e fases
├── adr/                       # decisões arquiteturais (ver o próprio índice: histórico vs. vigente)
└── legacy/                    # documentação da iteração multiagente descartada
.cursor/specs/faseN.spec.md   # spec de comportamento por fase — a mais próxima do código
```

## Segurança

- Não versione `.env` com segredos reais.
- Credenciais AWS reais nunca em texto plano no repositório — Secrets Manager/Parameter Store
  em nuvem, variáveis de ambiente locais em dev.
- Conteúdo de entidade do broker é tratado como dado não confiável no prompt do Nível 2
  (mitigação de prompt injection — ver `docs/plano_refatoracao_v3.md`, Parte III, 3.8).

## Licença

MIT — TCC Auditor de Conformidade FIWARE.
