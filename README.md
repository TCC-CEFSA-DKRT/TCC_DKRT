# DKRT — Context Broker Multiagent

Sistema multiagentes para operar o **FIWARE Orion Context Broker (NGSI-v2)** com CLI, SLM, RAG, guardrails e servidor **MCP**.

Documentação de fases: [`docs/fases/README.md`](docs/fases/README.md).

## Requisitos

- Python **3.11+**
- (Opcional) Docker — Orion local
- (Opcional) GPU/RAM — modelo `microsoft/phi-2` (`SLM_ENABLED=true`)

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

## Base de conhecimento (RAG — Fase 2)

```powershell
.\.venv\Scripts\python scripts/rag/chunk_hybrid.py knowledge/raw/ --out knowledge/chunks/ --category fiware
```

Gera `knowledge/chunks/chunks.jsonl` com pares **Small2Big**.

## Orion local (Fase 4 / 10)

```powershell
docker compose up -d
# Aguarde ~30s; verifique: http://localhost:1026/version
python scripts/seed_orion.py
```

Configure no `.env`:

```env
FIWARE_BROKER_URL=http://localhost:1026
FIWARE_SERVICE=openiot
FIWARE_SERVICE_PATH=/
```

## Terminal CLI externo (principal)

O DKRT **não é um programa com ícone na área de trabalho** (como um `.exe` instalador). É um **terminal de texto** — igual ao `ollama run` no PowerShell.

### Onde fica o “exe”?

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

**Abrir janela dedicada (recomendado para “CLI externo”):**

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
/query Sensor 20
/status
/model qwen2.5:3b
/help
/exit
```

| Comando no terminal | Função |
|---------------------|--------|
| *(texto livre)* | Conversa ou pedido FIWARE via SLM + agentes |
| `/help` | Lista comandos |
| `/exit`, `/quit` | Sair |
| `/clear` | Limpa histórico da sessão |
| `/history` | Últimas trocas |
| `/status` | Ollama + FIWARE Orion |
| `/agents` | Agentes disponíveis |
| `/model` ou `/model qwen2.5:3b` | Modelo SLM |
| `/query Sensor 20` | Consulta NGSI direta (sem SLM) |
| `/orchestrate texto` | Orquestrador multiagentes |

**Comportamento:** cumprimentos → resposta da IA (sem Orion). Pedidos sobre sensores → agentes + Orion. Dados faltando → IA pergunta antes de executar.

## Ferramentas administrativas (`dkrt-tools`)

Comandos one-shot (scripts, CI, automação):

| Comando | Descrição |
|---------|-----------|
| `dkrt-tools query -t Sensor` | Consulta NGSI direta |
| `dkrt-tools ask "listar sensores"` | NL + orquestração (one-shot) |
| `dkrt-tools orchestrate "..."` | Orquestrador |
| `dkrt-tools ollama-check` | Verifica Ollama |
| `dkrt-tools serve -p 8000` | Servidor MCP |

## Servidor MCP (Fase 7)

```powershell
dkrt serve --host 127.0.0.1 --port 8000
```

```powershell
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/mcp -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}"
```

Ferramentas: `dkrt_orchestrate`, `dkrt_query_entities`, `dkrt_interpret_nl`.

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
dkrt ask "listar todos os sensores de temperatura"
```

A saída deve mostrar `Interpretação (ollama): ...`.

**Fallback:** se Ollama estiver offline ou `SLM_ENABLED=false`, o sistema usa regras heurísticas (sem GPU).

### Alternativa: phi-2 via Transformers

```powershell
pip install -e ".[slm]"
# .env: SLM_PROVIDER=transformers, SLM_MODEL=microsoft/phi-2
```

## Guardrails (Fase 9)

Após gerar JSON de codegen:

```powershell
python scripts/rag/detect_pii.py --file resposta.json
python scripts/rag/validate_schema.py resposta.json
```

Schema: `schemas/codegen_output.schema.json`. Skills: `.cursor/skills/dkrt-code-guardrails/`.

## Testes (Fase 10)

```powershell
.\scripts\run_tests.ps1
# ou (com venv)
.\.venv\Scripts\python -m pytest tests/ -v -m "not integration"
```

Inclui orquestrador, SLM, FIWARE mock, RAG, MCP, CLI e guardrails (≥ 15 testes).

Testes com Orion real (opcional):

```powershell
pytest tests/ -v -m integration
```

## Estrutura do projeto

```
├── src/context_broker_multiagent/   # Pacote principal
│   ├── agents/                      # Route, Query, Subscribe, Provision, Analyze
│   ├── models/                      # Pydantic NGSI + mensagens
│   ├── services/                    # FIWARE, SLM, RAG, MCP
│   ├── orchestrator.py
│   └── cli.py
├── knowledge/raw/                   # Docs para ingestão
├── scripts/rag/                     # chunk_hybrid, PII, schema
├── prompts/                         # Ingestão, inferência, guardrails
├── schemas/
├── tests/
├── docs/fases/                      # Plano por fase (mantido)
└── .cursor/skills/                  # Skills Cursor DKRT
```

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
