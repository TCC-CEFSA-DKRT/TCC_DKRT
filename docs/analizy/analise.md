# DKRT — Diagnóstico Técnico e Plano de Refatoração

**Projeto:** `agent_multi_IA_context_broker` (DKRT — Context Broker Multiagent)
**Contexto:** TCC, 9º semestre, entrega final em ~12 meses, entregas parciais no caminho
**SLM utilizado:** Qwen2.5 via Ollama (local)
**Data:** agosto/2026 — versão consolidada e verificada contra o código-fonte

---

## 1. Resumo executivo

O projeto tem uma base técnica sólida (cliente FIWARE, modelos Pydantic, serviço de SLM com prompt bem estruturado, testes automatizados), mas sofreu **deriva arquitetural**: ao longo das fases do TCC, novas camadas foram adicionadas sem que as anteriores fossem consolidadas ou removidas. O resultado é um projeto com **duas implementações paralelas do mesmo domínio** que nunca se encontram, um parsing de resposta do SLM frágil demais para um modelo pequeno rodando localmente, e uma cobertura do backend FIWARE de referência (Orion + IoT Agent MQTT + histórico) ainda incompleta.

**Recomendação:** refatorar, não reescrever do zero. O núcleo (`FiwareClient`, `models/`, `SLMService`, `ChatEngine`) é reaproveitável.

---

## 2. Problemas identificados

### 2.1 Duas arquiteturas de agentes coexistindo, sem comunicação entre si

Verificado no código:

- **`orchestrator.py`** (`MultiAgentOrchestrator`) executa **todos** os agentes em paralelo via `asyncio.gather`, sempre — `RouteAgent`, `QueryAgent`, `SubscribeAgent`, `ProvisionAgent`, `AnalyzeAgent`. É usado pelos comandos `dkrt ask` e `dkrt orchestrate`.
- **`core/chat_engine.py` + `core/intent_router.py`** usam um **segundo** conjunto de agentes — `QueryAgent`, `ListAgent`, `CreateAgent`, `UpdateAgent`, `DeleteAgent` — escolhendo apenas um, com base na decisão do SLM (`IntentRouter._agents: dict[str, BaseAgent]`). É o fluxo usado pelo terminal interativo (`dkrt`), que é o modo "principal" segundo o próprio README.

**Impacto:** o fluxo que o usuário realmente usa (terminal) e o fluxo descrito como "orquestrador multiagentes" no README são sistemas desconectados. Isso gera confusão sobre qual é "a" arquitetura do projeto — inclusive para quem está desenvolvendo. Este ponto **substitui e refina** a observação anterior de "orquestrador central com SLM + handlers": na verdade existem *dois* orquestradores centrais, não um.

### 2.2 O orquestrador "multiagente" não usa o SLM — é classificação por palavra-chave

```python
# agents/route.py
if any(w in text for w in ("criar", "provision", "cadastrar", "inserir")):
    intent = "provision"
```

Não é necessariamente errado como *fallback*, mas contradiz a proposta central do projeto (usar IA/SLM para interpretar linguagem natural) quando é a via principal de decisão nesse fluxo.

### 2.3 Parsing frágil da resposta do SLM

```python
# services/slm_service.py
match = re.search(r"\{.*\}", raw, re.DOTALL)
if not match:
    raise OllamaError("JSON não encontrado na resposta do modelo")
data = json.loads(match.group())
```

Extrair JSON de texto livre por regex é arriscado com um modelo pequeno local: qualquer texto antes/depois do JSON, blocos de markdown (` ```json `), ou JSON malformado quebra o parsing e força o fallback heurístico. Isso provavelmente explica boa parte da percepção de "o SLM não entende bem os comandos" — o modelo pode estar respondendo corretamente, mas o parsing descarta a resposta.

### 2.4 Fallback heurístico superdimensionado

O método `_analyze_chat_heuristic` reimplementa, em regex e listas de palavras-chave, praticamente o mesmo classificador de intenção que o SLM deveria fazer. É uma rede de segurança valiosa, mas o volume de lógica sugere que está carregando peso demais no dia a dia — só um teste medido confirma isso (ver Bloco 2).

### 2.5 Escopo definido na Fase 0 é grande demais para um TCC individual

Multiagentes + integração NGSI-v2 + CLI + SLM + servidor MCP + pipeline RAG completo (ingestão + inferência em tempo real) + guardrails de segurança + suite de testes de integração é escopo típico de equipe, não de projeto solo — o que ajuda a explicar a deriva do planejamento.

### 2.6 Duplicação leve de entrypoints

`cli.py` (Typer), `terminal/shell.py` (shell interativo `prompt_toolkit`) e `repl/chat.py` coexistem. `repl/chat.py` já é um alias correto para `terminal/shell.py`, mas `cli.py` ainda expõe comandos (`ask`, `orchestrate`) que dependem do `MultiAgentOrchestrator` desalinhado do fluxo principal (ver 2.1).

### 2.7 Cobertura do backend FIWARE de referência ainda incompleta

**Confirmado no código:** hoje o projeto cobre apenas o **Orion Context Broker**, e mesmo assim parcialmente.

- `docker-compose.yml` só sobe `mongo` e `orion`.
- `config.py` só define `fiware_broker_url` — não há `iot_agent_url` nem URL de componente de histórico.
- `fiware_client.py` só implementa `/v2/entities` (create/query/update/delete/health).
- Nenhuma chamada às portas do IoT Agent MQTT (4041) ou de qualquer componente de histórico existe no repositório.
- `SubscribeAgent` monta o JSON da subscrição mas **não a envia** ao Orion (confirmado no código: retorna a mensagem `"Plano de subscrição NGSI-v2 gerado (não enviado ao Orion)"`).
- O prompt de sistema do SLM já admite explicitamente ao usuário que não há persistência histórica.

**Consequência prática:** hoje o sistema não sabe (a) provisionar um dispositivo IoT real que fala MQTT — só cria uma entidade abstrata direto no Orion, sem passar pelo IoT Agent — nem (b) consultar dados históricos/série temporal, porque a subscrição que alimentaria o componente de histórico nunca é enviada.

**Nota de escopo:** "cobrir 100% do FIWARE" não é um alvo bem definido — o ecossistema inclui dezenas de Generic Enablers (Keyrock, Wilma, Cygnus, IoT Agents para múltiplos protocolos, etc.). O objetivo deve ser formulado como **cobertura completa do backend de referência definido no diagrama do projeto**: Orion + IoT Agent MQTT + componente de histórico + banco de dados — um escopo fechado e defensável.

---

## 3. Decisão técnica: QuantumLeap no lugar de STH-Comet

**Esta seção corrige e substitui a recomendação anterior de usar STH-Comet.** Avaliadas as duas opções, o plano adota **QuantumLeap** como componente de persistência histórica, por ser o substituto ativamente mantido pela comunidade FIWARE (STH-Comet está em modo de manutenção). A troca implica mudanças em mais de um componente, não apenas no nome do cliente:

- **Banco de dados muda:** QuantumLeap persiste em **CrateDB** (SQL distribuído, não MongoDB) — a "segunda base Mongo (Historical)" do diagrama original é substituída por um container de CrateDB.
- **`docker-compose.yml`:** adicionar `crate-db` (imagem `crate`, portas 4200/4300) e `quantumleap` (imagem `orchestracities/quantumleap`, porta 8668, `CRATE_HOST=crate-db`). Não há mais um segundo Mongo.
- **Cliente de histórico é implementação nova**, não find-and-replace: a API do QuantumLeap tem rotas e formato de resposta diferentes do STH-Comet (mais próxima da sintaxe nativa do NGSI-v2/LD para consultas de série temporal).
- **`SubscribeAgent`:** a notificação enviada ao Orion aponta para `http://quantumleap:8668/v2/notify` (headers `fiware-service`/`fiware-servicepath` mantidos, com metadados `dateCreated`/`dateModified` na notificação).
- **Recomendação de design:** definir uma interface abstrata `HistoricalDataClient` (`Protocol`/`ABC` com método `query_history(entity_id, attr, last_n)`) e implementar o QuantumLeap atrás dela — assim `HistoryAgent` e o roteador de intenção nunca dependem de qual backend está por trás, e uma troca futura fica isolada num único arquivo.
- **Oportunidade adicional (fora do escopo obrigatório):** QuantumLeap combina naturalmente com Grafana (plugin de datasource do CrateDB) para visualização de série temporal — pode virar diferencial visual na apresentação, mas não é pré-requisito.

---

## 4. Plano de refatoração

### Bloco 1 — Consolidação da arquitetura (prioridade máxima)

1. **Unificar o vocabulário de operações** (`list`, `query`, `create`, `update`, `delete`, `subscribe`, `analyze`) em todo o projeto — router, agentes, prompts do SLM.
2. **Aposentar o `MultiAgentOrchestrator` do fluxo de decisão principal.** Pode continuar existindo como código de referência, mas `dkrt`, `dkrt ask` e `dkrt orchestrate` devem passar a usar o mesmo caminho de decisão (`ChatEngine` + `IntentRouter`).
3. **Fundir os dois conjuntos de `agents/`** em um só, usado por todos os entrypoints.
   *Critério de pronto:* todos os comandos do CLI compartilham a mesma lógica de decisão de agente.
4. **Implementar o loop de execução → verificação → correção** — o núcleo que diferencia o projeto de um simples CLI de comandos. Depois de executar uma ação (`create`/`update`/`delete`), o sistema verifica o resultado e, em caso de erro, tenta corrigir ou pede esclarecimento ao usuário, em vez de apenas reportar sucesso/falha.

   **Padrão de referência: ReAct** (Reasoning + Acting) — um único ponto de decisão via SLM que age, observa o resultado real da ação, e decide o próximo passo com base nessa observação. Não é "múltiplos agentes conversando entre si" (isso seria outro padrão, como AutoGen/CrewAI); é um loop de raciocínio que se repete algumas vezes até resolver ou escalar para o usuário.

   **Regra de ouro:** a *verificação* deve ser determinística (código puro, comparando o payload enviado com o resultado consultado — diff de campos), nunca delegada ao SLM. Deixar o modelo "julgar" se os dados batem introduz risco de alucinação. O SLM só volta a ser chamado **depois** que o código já determinou que houve erro — aí seu papel é interpretar a causa e decidir a correção ou formular a pergunta ao usuário.

   **Fluxo do loop:**
   ```
   SLM classifica intenção (extrai parâmetros em JSON)
            ↓
   Executa ação (chamada direta ao FIWARE)
            ↓
   Verifica resultado (re-consulta e compara — determinístico)
            ↓
      ┌─────┴─────┐
      ↓           ↓
   Sucesso    Erro detectado
      ↓           ↓
   Confirma   Corrige automaticamente (retry limitado, 2–3 tentativas)
   ao usuário     ou
              Pergunta ao usuário (pausa, guarda estado parcial, retoma na resposta)
   ```

   **Taxonomia de erros:**
   - *Corrigível automaticamente:* tipo de atributo incorreto (ex.: `Text` onde Orion espera `Number`), atributo obrigatório ausente com valor inferível pelo contexto, `entity_id` duplicado (sugerir sufixo). O SLM recebe a mensagem de erro do Orion como observação e tenta de novo, com limite de tentativas.
   - *Precisa do usuário:* dado realmente ausente e não inferível, ambiguidade real de `entity_type`, ou esgotamento das tentativas automáticas. O sistema pausa, guarda o estado parcial (o `ChatEngine` já tem um conceito de "pending" reaproveitável aqui), pergunta, e retoma quando o usuário responder.

   **Risco a controlar:** cada chamada adicional ao SLM no loop é um ponto onde um modelo pequeno local pode divergir da intenção original. Limite de tentativas curto (2–3, nunca loop infinito) e decisão "corrige vs. pergunta" o mais determinística possível.

   *Critério de pronto:* uma operação de `create` com dado inválido é detectada na verificação, corrigida automaticamente OU escalada para pergunta ao usuário — nunca apenas reportada como "erro" sem tentativa de recuperação.

### Bloco 2 — Robustez do SLM local

5. **Substituir o parsing por regex pelo modo JSON estruturado nativo do Ollama** (parâmetro `format` do endpoint `/api/chat`, com JSON Schema quando possível) — restringe a decodificação do próprio modelo ao formato esperado, crítico para um SLM pequeno.
6. **Construir um dataset de teste de 30–40 frases em PT-BR** representativas do uso real, com resultado esperado (`intent`, `entity_type`, etc.), e medir a acurácia do Qwen2.5 atual.
7. **Ajustar o prompt (`CHAT_ANALYSIS_PROMPT`)** com base nos erros reais observados — idealmente com exemplos few-shot das frases que falharam.
   *Critério de pronto:* taxa de fallback para heurística por erro de parsing próxima de zero (só deve cair na heurística se o Ollama estiver offline).

### Bloco 3 — Testes e validação do fluxo principal

8. **Atualizar os testes existentes** (`test_orchestrator.py`, `test_intent_router.py`, `test_chat_engine.py`, etc.) para refletir a arquitetura unificada.
9. **Testar o fluxo completo** (terminal + Ollama + Orion rodando localmente), cobrindo: conversa casual, pergunta conceitual, consulta, criação, e pedido de esclarecimento por dado faltante.

### Bloco 4 — RAG, MCP e guardrails (escopo completo, não opcional)

Fazem parte do escopo pleno do TCC e devem ser implementados por completo — a recomendação é sobre **ordem de implementação**, não redução de escopo.

10. **Pipeline RAG completo:** ingestão de conhecimento (`chunk_hybrid.py`, Small2Big), inferência em tempo real (rewrite + busca + rerank via `RagRetriever`), e integração com o fluxo de decisão do agente (contexto recuperado deve influenciar a resposta do SLM, não apenas ser exibido).

    > **Reforço conceitual:** o RAG é *recuperação de contexto documental* para melhorar respostas/geração — **não é aprendizado automático de novas integrações**. Acoplar uma ferramenta nova ao sistema (ex.: um novo Generic Enabler do FIWARE) é RAG + geração de código assistida + guardrails + revisão humana; não é "colar a documentação e o sistema passar a operar a ferramenta sozinho".

11. **Servidor MCP:** expor as ferramentas do domínio (`dkrt_orchestrate`, `dkrt_query_entities`, `dkrt_interpret_nl`) de forma estável, com testes de integração cobrindo o protocolo JSON-RPC.

    > **Extensibilidade futura:** hoje o catálogo de ferramentas do MCP (`TOOLS` em `services/mcp_server.py`) é uma lista hardcoded, duplicada manualmente do enum de intents (`models/intent.py`) e do prompt do SLM (`slm_service.py`) — três fontes de verdade separadas. A evolução recomendada é um **tool registry único**, do qual o enum, o prompt e a lista `TOOLS` são derivados automaticamente, e o SLM passa a consultar esse catálogo dinamicamente (function calling), em vez de depender de texto fixo no prompt. Isso torna "adicionar uma ferramenta nova" equivalente a "adicionar um item na lista", em vez de editar 3 arquivos desconexos.

12. **Guardrails e segurança:** detecção de PII, validação de schema (`codegen_output.schema.json`), e política de bloqueio/sanitização antes de ações destrutivas (`delete`, `update`) no Context Broker.

Implementar esses módulos **depois** que o Bloco 1–3 estiver estável evita retrabalho (vão se apoiar na arquitetura já unificada e no parsing robusto do SLM), mas nenhum deve ser cortado do projeto final.

### Bloco 5 — Cobertura do backend FIWARE de referência (Orion + IoT Agent MQTT + QuantumLeap)

13. **Cliente QuantumLeap** (`quantumleap_client.py`, implementando a interface `HistoricalDataClient`): consultas de série temporal por entidade/atributo com suporte a `lastN` e agregações (`aggrMethod`/`aggrPeriod`).
14. **Cliente IoT Agent MQTT** (`iot_agent_client.py`): provisionamento de grupo de serviço (`POST/GET/DELETE /iot/services`), provisionamento de dispositivo (`POST /iot/devices` — device_id, entity_name, atributos, mapeamento de tópicos MQTT), listagem/remoção de dispositivos, e registro de comandos (`POST /v2/registrations`).
15. **Implementar de fato o `SubscribeAgent`:** hoje só monta o plano; precisa enviar `POST /v2/subscriptions` ao Orion apontando para `http://quantumleap:8668/v2/notify` — sem isso, o QuantumLeap nunca recebe dados novos mesmo que o container exista.
16. **Novo `HistoryAgent`** (ou expandir o `QueryAgent`) para intenções do tipo "mostrar histórico/série temporal de X", consumindo `quantumleap_client.py` através da interface `HistoricalDataClient`.
17. **Expandir `config.py`:** `iot_agent_url`, `quantumleap_url`, `iot_service_group_apikey`, e demais variáveis dos novos clientes.
18. **Expandir `docker-compose.yml`:** `mosquitto` (broker MQTT), `iot-agent-mqtt`, `crate-db`, `quantumleap`.
19. **Expandir o `IntentRouter`:** hoje distingue apenas `query | list | create | update | delete`; precisa diferenciar "criar entidade direto no Orion" de "provisionar dispositivo real via IoT Agent" de "consultar histórico via QuantumLeap" — três operações com destinos e semânticas diferentes.

*Critério de pronto:* o usuário consegue, em linguagem natural, provisionar um dispositivo MQTT real (que aparece no IoT Agent e gera uma entidade correspondente no Orion) e consultar o histórico de um atributo desse dispositivo via QuantumLeap — os dois cenários hoje impossíveis.

**Dependência:** este bloco vem depois do Bloco 1 (arquitetura de agentes consolidada) e do Bloco 2 (parsing robusto do SLM) — os novos agentes (`HistoryAgent`, IoT Agent) devem nascer já dentro do registry unificado e do loop de verificação/correção do Bloco 1, não como mais uma ramificação paralela (repetindo o erro descrito em 2.1).

### Bloco 6 — Documentação e entrega

20. **Atualizar o README** para refletir o fluxo real e único (hoje descreve capacidades — orquestrador paralelo — que não correspondem ao que o terminal principal executa), incluindo a cobertura real do backend FIWARE (Orion + IoT Agent + QuantumLeap) após o Bloco 5.
21. Consolidar documentação técnica final e preparar roteiro de demonstração — idealmente um cenário de ponta a ponta: provisionar sensor → registrar leitura via MQTT → consultar estado atual → consultar histórico.

---

## 5. Roteiro sugerido para a próxima entrega parcial (4–6 semanas)

| Semana | Foco | Critério de pronto |
|---|---|---|
| 1 | Bloco 1 — unificar arquitetura de agentes | Todos os entrypoints usam o mesmo caminho de decisão |
| 2 | Bloco 2 — JSON estruturado no Ollama | Zero fallback por erro de parsing em teste manual |
| 3 | Bloco 2 — dataset de teste + ajuste de prompt | Acurácia do SLM medida e documentada |
| 4 | Bloco 3 — testes + ensaio da demo | Fluxo completo rodando de ponta a ponta, roteiro de demo definido |
| 5–6 | Buffer | Ajustes finais, imprevistos de ambiente (Windows/Ollama) |

---

## 6. Escopo completo do projeto

O escopo do TCC permanece integral: multiagentes (reformulado como orquestrador central com SLM + handlers, unificado — ver Bloco 1), integração NGSI-v2 (Orion), integração com IoT Agent MQTT e QuantumLeap/CrateDB (backend de referência completo do diagrama), CLI, SLM local, pipeline RAG completo, servidor MCP com tool registry evolutivo, e guardrails de segurança — todos fazem parte da entrega final, independentemente do tempo disponível.

A sequência proposta (Blocos 1–3 antes dos Blocos 4 e 5) é uma recomendação de **engenharia de software**, não de corte de escopo: construir sobre uma arquitetura de agentes já unificada, um parsing de SLM robusto e um loop de verificação/correção evita que RAG, MCP, guardrails e os novos clientes IoT Agent/QuantumLeap herdem os mesmos problemas de duplicação e fragilidade identificados na Seção 2. Cada bloco entregue de forma isolada e funcional também vira evidência concreta (métricas, logs, exemplos) para o capítulo correspondente da monografia.