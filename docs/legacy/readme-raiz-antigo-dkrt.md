> **Arquivo histórico.** Esta era a íntegra do `README.md` da raiz do repositório antes da reescrita (auditor de conformidade FIWARE). Descreve o sistema multiagente descartado — ver `docs/plano_refatoracao_v3.md` (Parte IV) e `docs/legacy/README.md`. O `README.md` atual da raiz reflete a arquitetura vigente.

---

> **Projeto renomeado: `fiware-conformance-auditor`.** O escopo mudou para um auditor de conformidade FIWARE (Orion x Smart Data Models), conforme `docs/plano_refatoracao_v3.md`. O conteudo abaixo ainda descreve o sistema anterior (DKRT) e sera reescrito conforme as fases da Parte V do plano forem entregues — ate la, use o plano como fonte de verdade.

# DKRT — Context Broker Multiagent

Sistema de agentes para operar o **FIWARE Orion Context Broker (NGSI-v2)** com CLI, SLM,
RAG, guardrails, backend de dados históricos (QuantumLeap + STH-Comet), provisionamento
de dispositivos IoT via MQTT e servidor **MCP**.

Documentação de fases: [`docs/fases/README.md`](docs/fases/README.md).
Documentação de decisões arquiteturais: [`docs/adr/`](docs/adr/) (ver seção
[Decisões de arquitetura](#decisões-de-arquitetura-adrs) abaixo).

## Requisitos

- Python **3.11+**
- Docker + Docker Compose — Orion, QuantumLeap, STH-Comet\*, IoT Agent MQTT locais
- (Opcional) GPU/RAM — modelo `microsoft/phi-2` (`SLM_ENABLED=true` + `SLM_PROVIDER=transformers`)

\* STH-Comet é opcional e não está no `docker-compose.yml` (é o backend legado — ver
[ADR-0010](docs/adr/adr-0010.md); só é necessário se você já tiver uma instância STH-Comet
existente para apontar via `.env`).

## Instalação rápida

No Windows, se `python` ou `pip` não forem reconhecidos, use o launcher **`py`** (Python 3.11 já instalado via instalador oficial):

```powershell
cd agent_multi_IA_context_broker
.\scripts\setup_windows.ps1
.\.venv\Scripts\Activate.ps1
```

Ou manualmente:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
```

> **Dica:** Desative o atalho da Microsoft Store em *Configurações → Aplicativos → Aliases de execução de aplicativo* e desligue `python.exe` / `python3.exe`, para o comando `python` apontar ao Python real após marcar "Add to PATH" no instalador.

## Base de conhecimento (RAG)

```powershell
.\.venv\Scripts\python scripts/rag/chunk_hybrid.py knowledge/raw/ --out knowledge/chunks/ --category fiware
```

Gera `knowledge/chunks/chunks.jsonl` com pares **Small2Big**.

> **Nota de arquitetura:** o RAG está disponível apenas em `dkrt-tools ask --rag` — o
> fluxo principal do chat (`dkrt`) classifica a intenção do usuário num vocabulário fixo
> de operações, sem consultar a base de conhecimento em tempo real. Essa decisão (e o
> porquê de não termos ido para um modo mais agentic com RAG) está documentada na
> [ADR-0000](docs/adr/adr-0000.md).

## Backend FIWARE completo (Orion + QuantumLeap + IoT Agent MQTT)

```powershell
docker compose up -d
docker compose ps   # aguarde todos os serviços ficarem "healthy" (~30-60s, principalmente crate-db)
python scripts/seed_orion.py
```

Serviços subidos pelo `docker-compose.yml`:

| Serviço | Porta | Papel |
|---|---|---|
| `mongo` | 27017 | Base de dados do Orion |
| `orion` | 1026 | Context Broker (NGSI-v2) |
| `crate-db` | 4200 / 4300 | Base de série temporal do QuantumLeap |
| `quantumleap` | 8668 | Persistência histórica (backend recomendado — [ADR-0003](docs/adr/adr-0003.md)) |
| `mosquitto` | 1883 | Broker MQTT para dispositivos IoT |
| `iot-agent-mqtt` | 4041 | Provisionamento de dispositivos MQTT ([ADR-0004](docs/adr/adr-0004.md)) |

Valide a conectividade de todos os backends de uma vez:

```powershell
python scripts/check_full_stack.py
```

Configure no `.env`:

```env
FIWARE_BROKER_URL=http://localhost:1026
FIWARE_SERVICE=openiot
FIWARE_SERVICE_PATH=/
QUANTUMLEAP_URL=http://localhost:8668
STH_COMET_URL=http://localhost:8666
IOT_AGENT_URL=http://localhost:4041
```

## Terminal CLI externo (principal)

O DKRT **não é um programa com ícone na área de trabalho** (como um `.exe` instalador). É um **terminal de texto** — igual ao `ollama run` no PowerShell.

### Onde fica o "exe"?

Após `pip install -e .`, o pip cria um atalho em:

```
.venv\Scripts\dkrt.exe
```

Esse arquivo **só funciona com o projeto instalado** (venv + Python). Não é um instalador independente.

### Como abrir (escolha uma opção)

| Onde | Como |
|------|------|
| **Janela nova fora do Cursor** | Dê duplo clique em `scripts\Iniciar-DKRT.bat` |
| **PowerShell externo** | Abra PowerShell → `cd` na pasta do projeto → `.\.venv\Scripts\Activate.ps1` → `dkrt` |
| **Terminal do Cursor** | Mesmo comando `dkrt` no painel Terminal (já é o CLI) |

```powershell
# Primeira vez (feche o dkrt se estiver rodando antes de reinstalar)
pip install -e .
```

**Abrir janela dedicada (recomendado para "CLI externo"):**

```text
Duplo clique:  scripts\Iniciar-DKRT.bat
```

Ou no PowerShell:

```powershell
.\scripts\Iniciar-DKRT.ps1
```

Prompt exibido: `dkrt> `

```
Bom dia
listar sensores do lab 64
provisione o sensor s1 no iot agent via mqtt
/query Sensor 20
/status
/model qwen2.5:3b
/help
/exit
```

| Comando no terminal | Função |
|---------------------|--------|
| *(texto livre)* | Conversa ou pedido FIWARE via SLM + agentes (query, list, create, update, delete, subscribe, iot_provision) |
| `/help` | Lista comandos |
| `/exit`, `/quit` | Sair |
| `/clear` | Limpa histórico da sessão |
| `/history` | Últimas trocas |
| `/status` | Ollama + FIWARE Orion |
| `/agents` | Agentes disponíveis |
| `/model` ou `/model qwen2.5:3b` | Modelo SLM |
| `/query Sensor 20` | Consulta NGSI direta (sem SLM) |
| `/orchestrate texto` | Classifica e despacha via `IntentRouter` (despachante único — [ADR-0001](docs/adr/adr-0001.md)) |

**Comportamento:** cumprimentos → resposta da IA (sem Orion). Pedidos sobre sensores → agentes + Orion, com verificação pós-execução automática ([ADR-0002](docs/adr/adr-0002.md)). Dados faltando → IA pergunta antes de executar. Se o SLM estiver indisponível, um classificador determinístico por palavra-chave assume como *fallback* ([ADR-0007](docs/adr/adr-0007.md)).

## Ferramentas administrativas (`dkrt-tools`)

Comandos one-shot (scripts, CI, automação):

| Comando | Descrição |
|---------|-----------|
| `dkrt-tools query -t Sensor` | Consulta NGSI direta |
| `dkrt-tools ask "listar sensores"` | Interpreta NL e despacha via `IntentRouter` (one-shot); `--rag` recupera contexto da base de conhecimento antes |
| `dkrt-tools orchestrate "..."` | Alias de `ask` sem `--rag` |
| `dkrt-tools ollama-check` | Verifica Ollama |
| `dkrt-tools agents` | Lista as operações registradas em `AGENT_REGISTRY` |
| `dkrt-tools serve -p 8000` | Servidor MCP |

## Servidor MCP

```powershell
dkrt serve --host 127.0.0.1 --port 8000
```

```powershell
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/mcp -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}"
```

Ferramentas: `dkrt_orchestrate` (interpreta NL e despacha via `IntentRouter`), `dkrt_query_entities`, `dkrt_interpret_nl`.

## SLM com Ollama + Qwen2.5 (recomendado)

1. Instale e inicie o [Ollama](https://ollama.com/):

```powershell
ollama serve
ollama pull qwen2.5
ollama list
```

Se `ollama` não for reconhecido no PowerShell, abra o **Ollama Desktop** (ícone na bandeja) — o serviço em `http://localhost:11434` sobe automaticamente.

2. Configure o `.env` (copie de `.env.example`):

```env
SLM_ENABLED=true
SLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5
```

> Use o nome **exato** retornado por `ollama list` (ex.: `qwen2.5:7b`, `qwen2.5:latest`).

3. Teste a conexão e interprete um pedido:

```powershell
dkrt ollama-check
dkrt-tools ask "listar todos os sensores de temperatura"
```

A saída deve mostrar `Interpretação (ollama): ...`.

**Fallback:** se Ollama estiver offline, `SLM_ENABLED=false`, ou a chamada ao modelo falhar (`SLMUnavailableError`), o `ChatEngine` cai automaticamente no classificador determinístico por palavra-chave (`RouteDispatcher.classify`, [ADR-0007](docs/adr/adr-0007.md)) — sem GPU, sem depender de rede.

### Alternativa: phi-2 via Transformers

```powershell
pip install -e ".[slm]"
# .env: SLM_PROVIDER=transformers, SLM_MODEL=microsoft/phi-2
```

## Guardrails

Após gerar JSON de codegen:

```powershell
python scripts/rag/detect_pii.py --file resposta.json
python scripts/rag/validate_schema.py resposta.json
```

Schema: `schemas/codegen_output.schema.json`. Skills: `.cursor/skills/dkrt-code-guardrails/`.

## Testes

```powershell
.\scripts\run_tests.ps1
# ou (com venv)
.\.venv\Scripts\python -m pytest tests/ -v -m "not integration"
```

57 testes cobrindo: classificação (SLM + fallback determinístico), roteamento (`IntentRouter`),
loop de verificação/retry (`ActionExecutor`, [ADR-0002](docs/adr/adr-0002.md)), pós-processamento
(`AnalyzeHandler`), CLI, terminal interativo e guardrails.

Testes com backend real (Orion/QuantumLeap/IoT Agent via `docker compose up`, opcional):

```powershell
pytest tests/ -v -m integration
```

## Frontend (Angular) — Fase 8

Cinco telas (Dashboard, Audit Runs, Report Detail, Natural Language, Catalog) contra a
API REST das Fases 4/5/8, em `frontend/` (Angular 19, standalone components, signals,
sem NgRx). Ver `.cursor/specs/fase8.spec.md` e `docs/design/design-system.md`.

```powershell
cd frontend
npm install
npm start          # ng serve — http://localhost:4200, contra a API em http://localhost:8000
npm test           # ng test — Karma/Jasmine (ChromeHeadless)
npm run build      # ng build — build de produção em dist/frontend
```

A API precisa estar rodando (`uvicorn auditor.interfaces.rest.app:app`) com CORS liberado
para `http://localhost:4200` — já é o padrão de `CORS_ALLOWED_ORIGINS` em `.env.example`.
Tenant (`Fiware-Service`/`Fiware-ServicePath`) é fixo em tempo de build em
`frontend/src/app/core/api-config.ts` (não há tela de login nesta fase).

## Infraestrutura AWS (Terraform) — Fase 9

Módulos e ambientes em `infra/terraform/` (`modules/{network,database,queue,compute,secrets}`,
`environments/{academy,production}`). Ver `.cursor/specs/fase9.spec.md` e
`docs/adr/adr-0013.md` (decisão Ollama-EC2 vs. Bedrock).

**Estado desta fase:** todo o código Terraform foi escrito e validado localmente
(sintaxe HCL + inspeção estrutural), mas **nenhum `terraform apply` real foi
executado contra a AWS** nesta sessão de trabalho — por decisão do usuário
("só escrever e validar localmente por agora"), sem credenciais fornecidas.
Rodar de verdade fica para quando o usuário tiver uma sessão ativa da AWS
Academy Learner Lab.

```bash
cd infra/terraform/environments/academy
# 1. Uma única vez por conta/sessão da Academy:
./scripts/bootstrap_backend.sh us-east-1 <bucket-unico> <tabela-dynamodb>
# 2. Exportar as credenciais temporárias do painel "AWS Details" do Learner Lab
#    (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN)
terraform init -backend-config="bucket=<bucket-unico>" \
  -backend-config="key=academy/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=<tabela-dynamodb>"
terraform plan
terraform apply
```

A instância Ollama nasce ligada (para baixar o modelo uma vez) mas nunca fica
ligada por padrão depois disso — use `scripts/start_ollama.sh <instance-id>` e
`scripts/stop_ollama.sh <instance-id>` explicitamente ao redor de cada
experimento (Fase 10), para não consumir crédito da Academy com a instância
ociosa.

CI (`.github/workflows/terraform-and-audit.yml`): `terraform plan` em PRs que
tocam `infra/terraform/`, `terraform apply` manual (aprovação obrigatória) via
`workflow_dispatch`, e `pip-audit` sobre `requirements.txt` — fechando uma
lacuna de segurança em aberto desde a Fase 0. Lint/type-check completos
continuam fora de escopo (débito conhecido, não bloqueante).

## Estrutura do projeto

```
├── src/context_broker_agent/
│   ├── agents/                 # Handlers por operação (Registry pattern, ADR-0001)
│   │   ├── registry.py             # AGENT_REGISTRY — fonte única de verdade do vocabulário
│   │   ├── base.py                 # BaseAgent (contrato process/verify/handle_error)
│   │   ├── query_handler.py, list_handler.py, create_handler.py,
│   │   │   update_handler.py, delete_handler.py, subscribe_handler.py,
│   │   │   iot_provision_handler.py
│   │   ├── dispatcher.py           # RouteDispatcher — fallback determinístico (ADR-0007)
│   │   └── analyze.py              # AnalyzeHandler — pós-processamento (ADR-0009)
│   ├── core/
│   │   ├── chat_engine.py          # Motor do chat: SLM → fallback → router → analyze
│   │   ├── intent_router.py        # Despachante único (ADR-0001)
│   │   └── action_executor.py      # Loop de verificação + retry (ADR-0002)
│   ├── models/                     # Pydantic: ChatIntent, AgentResponse, NGSI, etc.
│   ├── services/
│   │   ├── fiware_client.py            # Orion (entidades + subscrições)
│   │   ├── quantumleap_client.py       # Histórico (novo, ADR-0003)
│   │   ├── sth_comet_client.py         # Histórico (legado, ADR-0010)
│   │   ├── historical_backend_resolver.py  # Decide QuantumLeap vs STH-Comet (ADR-0010)
│   │   ├── iot_agent_client.py         # Provisionamento MQTT (ADR-0004/0012)
│   │   ├── slm_service.py, ollama_client.py, llama_cpp_service.py
│   │   ├── rag_retrieve.py
│   │   └── mcp_server.py
│   ├── terminal/                   # Terminal interativo (dkrt)
│   └── cli.py                      # Ferramentas administrativas (dkrt-tools)
├── docs/
│   ├── adr/                        # Decisões de arquitetura (ver seção abaixo)
│   └── fases/                      # Plano por fase do TCC
├── knowledge/raw/                  # Docs para ingestão (RAG)
├── scripts/                        # rag/, seed_orion.py, check_full_stack.py
├── prompts/
├── schemas/
└── tests/
```

## Decisões de arquitetura (ADRs)

Cada decisão estrutural relevante do projeto está registrada em
[`docs/adr/`](docs/adr/), seguindo o formato [ADR](docs/adr/template.md)
(Contexto → Decisão → Alternativas consideradas → Consequências):

| ADR | Decisão |
|---|---|
| [0000](docs/adr/adr-0000.md) | Orquestração determinística com SLM classificador, em vez de agente aberto (RAG/fine-tuning) — leitura recomendada primeiro |
| [0001](docs/adr/adr-0001.md) | Unificação da arquitetura de agentes (Registry pattern, `IntentRouter` único) |
| [0002](docs/adr/adr-0002.md) | Loop de execução com verificação determinística e retry (ReAct) |
| [0003](docs/adr/adr-0003.md) | QuantumLeap como backend de dados históricos |
| [0004](docs/adr/adr-0004.md) | Backend de referência completo (Orion + IoT Agent MQTT + QuantumLeap) |
| [0005](docs/adr/adr-0005.md) | Escopo do loop de verificação (mutações vs. leituras) |
| [0006](docs/adr/adr-0006.md) | Convenção de nomenclatura Handler/Dispatcher |
| [0007](docs/adr/adr-0007.md) | `RouteDispatcher` como fallback determinístico |
| [0008](docs/adr/adr-0008.md) | `SubscribeHandler` — subscrições NGSI-v2 reais |
| [0009](docs/adr/adr-0009.md) | `AnalyzeHandler` como pós-processamento, não operação roteável |
| [0010](docs/adr/adr-0010.md) | Coexistência STH-Comet (legado) e QuantumLeap (novo) |
| [0012](docs/adr/adr-0012.md) | IoT Agent MQTT como sétima operação do vocabulário (`iot_provision`) |
| [0013](docs/adr/adr-0013.md) | Ollama em EC2 (não Bedrock) como SLM de produção |

## Segurança

- Não versione `.env` com segredos reais.
- Use placeholders em exemplos (`user@example.com`, `localhost:1026`).
- Bind MCP em `127.0.0.1` em desenvolvimento.

## Skills Cursor

| Skill | Fase |
|-------|------|
| `dkrt-knowledge-ingestion` | 2 |
| `dkrt-rag-inference` | 8 |
| `dkrt-code-guardrails` | 9 |
| `dkrt-tcc-codegen` | Pipeline completo |

## Licença

MIT — TCC DKRT.