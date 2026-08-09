# DKRT — Diagnóstico Técnico e Plano de Refatoração

**Projeto:** `agent_multi_IA_context_broker` (DKRT — Context Broker Multiagent)
**Contexto:** TCC, 9º semestre, entrega final em ~12 meses, entregas parciais no caminho
**SLM utilizado:** Qwen2.5 via Ollama (local)
**Data do diagnóstico:** agosto/2026

---

## 1. Resumo executivo

O projeto tem uma base técnica sólida (cliente FIWARE, modelos Pydantic, serviço de SLM com prompt bem estruturado, testes automatizados), mas sofreu **deriva arquitetural**: ao longo das fases do TCC, novas camadas foram adicionadas sem que as anteriores fossem consolidadas ou removidas. O resultado é um projeto com **duas implementações paralelas do mesmo domínio** que nunca se encontram, e um parsing de resposta do SLM frágil demais para um modelo pequeno rodando localmente.

**Recomendação:** refatorar, não reescrever do zero. O núcleo (`FiwareClient`, `models/`, `SLMService`, `ChatEngine`) é reaproveitável.

---

## 2. Problemas identificados

### 2.1 Duas arquiteturas de agentes coexistindo, sem comunicação entre si

- `orchestrator.py` (`MultiAgentOrchestrator`) executa **todos** os agentes em paralelo via `asyncio.gather`, sempre — `RouteAgent`, `QueryAgent`, `SubscribeAgent`, `ProvisionAgent`, `AnalyzeAgent`. É usado pelos comandos `dkrt ask` e `dkrt orchestrate`.
- `core/chat_engine.py` + `core/intent_router.py` usam um **segundo** conjunto de agentes — `QueryAgent`, `ListAgent`, `CreateAgent`, `UpdateAgent`, `DeleteAgent` — escolhendo apenas um, com base na decisão do SLM. É o fluxo usado pelo terminal interativo (`dkrt`), que é o modo "principal" segundo o próprio README.

**Impacto:** o fluxo que o usuário realmente usa (terminal) e o fluxo descrito como "orquestrador multiagentes" no README são sistemas desconectados. Isso gera confusão sobre qual é "a" arquitetura do projeto — inclusive para quem está desenvolvendo.

### 2.2 O orquestrador "multiagente" não usa o SLM — é classificação por palavra-chave

```python
# agents/route.py
if any(w in text for w in ("criar", "provision", "cadastrar", "inserir")):
    intent = "provision"
```

Isso não é necessariamente errado como *fallback*, mas contradiz a proposta central do projeto (usar IA/SLM para interpretar linguagem natural) quando é a via principal de decisão.

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

O método `_analyze_chat_heuristic` reimplementa, em regex e listas de palavras-chave, praticamente o mesmo classificador de intenção que o SLM deveria fazer. Isso é uma rede de segurança valiosa (bom ter fallback), mas o volume de lógica sugere que ele está carregando peso demais no dia a dia — o que só um teste medido (ver item 3.3) vai confirmar.

### 2.5 Escopo definido na Fase 0 é grande demais para um TCC individual

O escopo original inclui: multiagentes + integração NGSI-v2 + CLI + SLM + servidor MCP + pipeline RAG completo (ingestão + inferência em tempo real) + guardrails de segurança + suite de testes de integração. Isso é escopo típico de um produto de equipe, não de um projeto de conclusão de curso solo — o que ajuda a explicar por que "o planejamento não saiu como planejado".

### 2.6 Duplicação leve de entrypoints

`cli.py` (Typer), `terminal/shell.py` (shell interativo `prompt_toolkit`) e `repl/chat.py` coexistem. `repl/chat.py` já é apenas um alias para `terminal/shell.py` (isso está correto), mas `cli.py` ainda expõe comandos (`ask`, `orchestrate`) que dependem do `MultiAgentOrchestrator` desalinhado do fluxo principal (ver 2.1).

---

## 3. Plano de refatoração

### Bloco 1 — Consolidação da arquitetura (prioridade máxima)

1. **Unificar o vocabulário de operações.** Escolher um único conjunto (`list`, `query`, `create`, `update`, `delete`, `subscribe`, `analyze`) e usá-lo em todo o projeto — router, agentes, prompts do SLM.
2. **Aposentar o `MultiAgentOrchestrator` do fluxo de decisão principal.** Pode continuar existindo como código de referência, mas `dkrt`, `dkrt ask` e `dkrt orchestrate` devem passar a usar o mesmo caminho de decisão (`ChatEngine` + `IntentRouter`).
3. **Fundir os dois conjuntos de `agents/`** em um só, usado por todos os entrypoints.
   *Critério de pronto:* todos os comandos do CLI compartilham a mesma lógica de decisão de agente.

4. **Implementar o loop de execução → verificação → correção.** Este é o núcleo do que diferencia o projeto de um simples CLI de comandos: depois de executar uma ação (`create`/`update`/`delete`), o sistema deve verificar o resultado e, em caso de erro, tentar corrigir ou pedir esclarecimento ao usuário, em vez de apenas reportar sucesso/falha.

   **Padrão de referência:** isto é o padrão **ReAct** (Reasoning + Acting) — um único ponto de decisão via SLM que age, observa o resultado real da ação, e decide o próximo passo com base nessa observação. Não é "múltiplos agentes conversando entre si" (esse seria outro padrão, como o usado por frameworks tipo AutoGen/CrewAI); é um loop de raciocínio que se repete algumas vezes até resolver ou escalar para o usuário.

   **Regra de ouro:** a *verificação* deve ser determinística (código puro, comparando o payload enviado com o resultado consultado — um diff de campos), nunca delegada ao SLM. Deixar o modelo "julgar" se os dados batem introduz risco de alucinação (ele pode achar que bateu quando não bateu). O SLM só volta a ser chamado **depois** que o código já determinou que houve erro — aí seu papel é interpretar a causa do erro e decidir a correção ou formular a pergunta ao usuário.

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

   **Taxonomia de erros (para decidir correção automática vs. pergunta ao usuário):**
   - *Corrigível automaticamente:* tipo de atributo incorreto (ex: mandou `Text` onde Orion espera `Number`), atributo obrigatório ausente com valor inferível pelo contexto, `entity_id` duplicado (sugerir sufixo). O SLM recebe a mensagem de erro do Orion como observação e tenta de novo, com limite de tentativas.
   - *Precisa do usuário:* dado realmente ausente e não inferível, ambiguidade real de `entity_type`, ou esgotamento das tentativas automáticas. O sistema pausa, guarda o estado parcial da operação (o `ChatEngine` já tem um conceito de "pending" que pode ser reaproveitado aqui), pergunta, e retoma quando o usuário responder.

   **Risco a controlar:** cada chamada adicional ao SLM no loop é um ponto onde um modelo pequeno local pode divergir da intenção original do usuário. Por isso, limite de tentativas curto (2–3, nunca loop infinito) e a decisão "corrige automaticamente vs. pergunta" deve ser o mais determinística possível (baseada no *tipo* de erro classificado, não numa nova interpretação livre do SLM a cada rodada).

   *Critério de pronto:* uma operação de `create` com dado inválido (ex: tipo de atributo errado) é detectada na verificação, corrigida automaticamente OU escalada para pergunta ao usuário — nunca simplesmente reportada como "erro" sem tentativa de recuperação.

### Bloco 2 — Robustez do SLM local

4. **Substituir o parsing por regex pelo modo JSON estruturado nativo do Ollama** (parâmetro `format` do endpoint `/api/chat`, com JSON Schema quando possível). Isso restringe a decodificação do próprio modelo ao formato esperado, em vez de depender do modelo "se comportar bem" — crítico para um SLM pequeno.
5. **Construir um dataset de teste de 30–40 frases em PT-BR** representativas do uso real, com o resultado esperado (`intent`, `entity_type`, etc.), e medir a acurácia do Qwen2.5 atual.
6. **Ajustar o prompt (`CHAT_ANALYSIS_PROMPT`)** com base nos erros reais observados no passo 5 — idealmente incluindo exemplos few-shot das frases que falharam.
   *Critério de pronto:* taxa de fallback para heurística por erro de parsing próxima de zero (só deve cair na heurística se o Ollama estiver offline).

### Bloco 3 — Testes e validação do fluxo principal

7. **Atualizar os testes existentes** (`test_orchestrator.py`, `test_intent_router.py`, `test_chat_engine.py`, etc.) para refletir a arquitetura unificada.
8. **Testar o fluxo completo** (terminal + Ollama + Orion rodando localmente) do jeito que será apresentado, cobrindo: conversa casual, pergunta conceitual, consulta, criação, e pedido de esclarecimento por dado faltante.

### Bloco 4 — RAG, MCP e guardrails (escopo completo, não opcional)

Esses três módulos fazem parte do escopo pleno do TCC e devem ser implementados por completo — a recomendação abaixo é sobre **ordem de implementação**, não sobre redução de escopo.

9. **Pipeline RAG completo:** ingestão de conhecimento (`chunk_hybrid.py`, Small2Big), inferência em tempo real (rewrite + busca + rerank via `RagRetriever`), e integração com o fluxo de decisão do agente (o contexto recuperado deve influenciar a resposta do SLM, não apenas ser exibido).
10. **Servidor MCP:** expor as ferramentas do domínio (`dkrt_orchestrate`, `dkrt_query_entities`, `dkrt_interpret_nl`) de forma estável, com testes de integração cobrindo o protocolo JSON-RPC.
11. **Guardrails e segurança:** detecção de PII, validação de schema (`codegen_output.schema.json`), e qualquer política de bloqueio/sanitização antes de ações destrutivas (`delete`, `update`) no Context Broker.

Implementar esses módulos **depois** que o Bloco 1–3 estiver estável evita retrabalho (eles vão se apoiar na arquitetura já unificada de agentes e no parsing robusto do SLM), mas nenhum deles deve ser cortado do projeto final.

### Bloco 5 — Cobertura do backend FIWARE de referência (Orion + IoT Agent MQTT + QuantumLeap)

**Diagnóstico (verificado no código em agosto/2026):** o projeto hoje cobre apenas o **Orion Context Broker**, e mesmo assim parcialmente. O `docker-compose.yml` só sobe `mongo` e `orion`; `config.py` só define `fiware_broker_url`; `fiware_client.py` só implementa `/v2/entities` (create/query/update/delete/health). Não há nenhuma chamada às portas 4041 (IoT Agent MQTT) ou de histórico em todo o repositório. O `SubscribeAgent` monta o JSON da subscrição mas **não a envia** ao Orion (confirmado no próprio código: `"Plano de subscrição NGSI-v2 gerado (não enviado ao Orion)"`), e o prompt do sistema do SLM já admite explicitamente ao usuário que não há persistência histórica.

Isso significa que, hoje, o sistema não sabe (a) provisionar um dispositivo IoT real que fala MQTT — só cria uma entidade abstrata direto no Orion, sem passar pelo IoT Agent — nem (b) consultar dados históricos/série temporal, porque a subscription que alimentaria o componente de histórico nunca é enviada.

**Nota de escopo:** "cobrir 100% do FIWARE" não é um alvo bem definido — o ecossistema FIWARE inclui dezenas de Generic Enablers (Keyrock, Wilma, Cygnus, IoT Agents para múltiplos protocolos, etc.). O objetivo aqui deve ser formulado como **cobertura completa do backend de referência definido no diagrama do projeto**: Orion + IoT Agent MQTT + componente de histórico + banco de dados — um escopo fechado e defensável.

**Decisão técnica — QuantumLeap em vez de STH-Comet:** avaliadas as duas opções, o plano adota **QuantumLeap** como componente de persistência histórica, por ser o substituto ativamente mantido pela comunidade FIWARE (STH-Comet está em modo de manutenção). Essa troca implica mudanças em mais de um componente, não apenas no nome do cliente:

- **Banco de dados muda:** QuantumLeap persiste em **CrateDB** (banco SQL distribuído, não MongoDB) — o plano de "segunda base Mongo (Historical)" do diagrama original é substituído por um container de CrateDB.
- **`docker-compose.yml`:** adicionar serviço `crate-db` (imagem `crate`, portas 4200/4300) e serviço `quantumleap` (imagem `orchestracities/quantumleap`, porta 8668, `CRATE_HOST=crate-db`). Não há mais um segundo Mongo.
- **Cliente de histórico é uma implementação nova**, não um find-and-replace: a API do QuantumLeap tem rotas e formato de resposta diferentes do STH-Comet (mais próxima da sintaxe nativa do NGSI-v2/LD para consultas de série temporal).
- **`SubscribeAgent`:** a notificação enviada ao Orion aponta para `http://quantumleap:8668/v2/notify` (headers `fiware-service`/`fiware-servicepath` mantidos, com metadados `dateCreated`/`dateModified` na notificação).
- **Recomendação de design:** definir uma interface abstrata `HistoricalDataClient` (`Protocol`/`ABC` com um método como `query_history(entity_id, attr, last_n)`) e implementar o QuantumLeap atrás dela — assim, `HistoryAgent` e `IntentRouter` nunca dependem de qual backend está por trás, e uma eventual troca futura fica isolada num único arquivo.
- **Oportunidade adicional (fora do escopo obrigatório):** QuantumLeap combina naturalmente com Grafana para visualização de série temporal via plugin de datasource do CrateDB — pode virar um diferencial visual para a apresentação, mas não é pré-requisito do Bloco 5.

12. **Cliente QuantumLeap** (`quantumleap_client.py`, implementando a interface `HistoricalDataClient`): consultas de série temporal por entidade/atributo com suporte a `lastN` e agregações (`aggrMethod`/`aggrPeriod`).
13. **Cliente IoT Agent MQTT** (`iot_agent_client.py`): implementar provisionamento de grupo de serviço (`POST/GET/DELETE /iot/services`), provisionamento de dispositivo (`POST /iot/devices` — device_id, entity_name, atributos, mapeamento de tópicos MQTT), listagem e remoção de dispositivos, e registro de comandos (`POST /v2/registrations`).
14. **Implementar de fato o `SubscribeAgent`**: hoje ele só monta o plano; precisa enviar `POST /v2/subscriptions` ao Orion apontando para o QuantumLeap (`http://quantumleap:8668/v2/notify`) — sem isso, o QuantumLeap nunca recebe dados novos mesmo que o container exista.
15. **Novo `HistoryAgent`** (ou expandir o `QueryAgent`) para tratar intenções do tipo "mostrar histórico/série temporal de X", consumindo o `quantumleap_client.py` através da interface `HistoricalDataClient`.
16. **Expandir `config.py`**: adicionar `iot_agent_url`, `quantumleap_url`, `iot_service_group_apikey`, e demais variáveis necessárias para os novos clientes.
17. **Expandir `docker-compose.yml`**: adicionar containers `mosquitto` (broker MQTT), `iot-agent-mqtt`, `crate-db` e `quantumleap`.
18. **Expandir o `IntentRouter`/roteador de intenção**: hoje ele distingue apenas `query | provision | subscribe | analyze`; precisa diferenciar "criar entidade direto no Orion" de "provisionar dispositivo real via IoT Agent" de "consultar histórico via QuantumLeap" — são três operações com destinos e semânticas diferentes.

*Critério de pronto:* o usuário consegue, em linguagem natural, provisionar um dispositivo MQTT real (que aparece no IoT Agent e gera uma entidade correspondente no Orion) e consultar o histórico de um atributo desse dispositivo (via QuantumLeap) — os dois cenários que hoje são impossíveis.

**Dependência:** este bloco deve vir depois do Bloco 1 (arquitetura de agentes consolidada) e do Bloco 2 (parsing robusto do SLM), pelo mesmo motivo dos demais — os novos agentes (`HistoryAgent`, IoT Agent) devem nascer já dentro do registry unificado e do loop de verificação/correção descrito no Bloco 1, não como mais uma ramificação paralela.

### Bloco 6 — Documentação e entrega

19. **Atualizar o README** para refletir o fluxo real e único (hoje ele descreve capacidades — orquestrador paralelo — que não correspondem ao que o terminal principal executa), incluindo a cobertura real do backend FIWARE (Orion + IoT Agent + QuantumLeap) após o Bloco 5.
20. Consolidar documentação técnica final e preparar roteiro de demonstração — incluindo, se possível, um cenário de ponta a ponta: provisionar sensor → registrar leitura via MQTT → consultar estado atual → consultar histórico.

---

## 4. Roteiro sugerido para a próxima entrega parcial (4–6 semanas)

| Semana | Foco | Critério de pronto |
|---|---|---|
| 1 | Bloco 1 — unificar arquitetura de agentes | Todos os entrypoints usam o mesmo caminho de decisão |
| 2 | Bloco 2 — JSON estruturado no Ollama | Zero fallback por erro de parsing em teste manual |
| 3 | Bloco 2 — dataset de teste + ajuste de prompt | Acurácia do SLM medida e documentada |
| 4 | Bloco 3 — testes + ensaio da demo | Fluxo completo rodando de ponta a ponta, roteiro de demo definido |
| 5–6 | Buffer | Ajustes finais, imprevistos de ambiente (Windows/Ollama) |

---

## 5. Escopo completo do projeto

O escopo do TCC permanece integral: multiagentes, integração NGSI-v2 (Orion), integração com IoT Agent MQTT e QuantumLeap/CrateDB (backend de referência completo do diagrama do projeto), CLI, SLM local, pipeline RAG completo, servidor MCP e guardrails de segurança — todos fazem parte da entrega final, independentemente do tempo disponível.

A sequência proposta neste documento (Blocos 1–3 antes dos Blocos 4 e 5) é uma recomendação de **engenharia de software**, não de corte de escopo: construir sobre uma arquitetura de agentes já unificada, um parsing de SLM robusto e um loop de verificação/correção evita que RAG, MCP, guardrails e os novos clientes IoT Agent/STH-Comet herdem os mesmos problemas de duplicação e fragilidade identificados na Seção 2. Cada bloco entregue de forma isolada e funcional também vira evidência concreta (métricas, logs, exemplos) para o capítulo correspondente da monografia.