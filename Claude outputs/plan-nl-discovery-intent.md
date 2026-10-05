# Plano: intenção de descoberta na tela Natural Language

## 0. O que confere e o que corrigi na proposta inicial

| # | Ponto | Situação |
|---|---|---|
| Contexto | "Dashboard consome `GET /entity-types`" | **Errado.** O único consumidor no frontend é `frontend/src/app/features/config/config.component.ts:81`, usando o tipo `EntityTypesResponse` de `shared/models/config.models.ts`. O dashboard não usa. Não muda nada no plano, porque não vamos reaproveitar esse serviço. |
| 1 | `intent`, `discovered_types` e `broker_reachable` no dataclass | Confere. Os 3 campos precisam entrar **no fim** e com default. Todo `AuditCommandInterpretation(...)` que já existe (fakes de teste, `_fallback`, router test) passa só os 4 campos atuais e continua funcionando. Use `Literal["audit", "discovery"]` como tipo de `intent`. `Literal` precisa ser importado de `typing` no port; em `schemas.py` ele já está importado. |
| 3 | "intent ausente ou inválido cai em fallback audit" | **São dois comportamentos diferentes, e o plano precisa separar:** (a) **ausente**: o default do Pydantic vira `"audit"` e o `entity_type` extraído é **preservado**. É o caso de hoje e mantém a compatibilidade. (b) **inválido** (`"list"`, `"Discovery"`, `null`): dá `ValidationError`, cai no `_fallback()` e zera tudo (`entity_type=None`, `confidence=0.0`, `intent="audit"`). Isso segue o contrato atual de "saída que não valida vira não entendi". |
| 3 | Falta proteção | **Acréscimo:** quando `intent == "discovery"`, o adaptador anula `entity_type` e `entity_id` em vez de confiar que o modelo obedeça o prompt. É uma linha e mantém a resposta da API coerente. |
| 4 | Use case com `context_broker` e `replace()` | Confere. Pegar **só** `ContextBrokerUnavailableError`, igual a `routers/entity_types.py`. `TenantBrokerNotConfiguredError` (SaaS sem conta cadastrada) deve **propagar**: o handler global em `interfaces/rest/app.py:90-118` já transforma em 401, igual ao `/entity-types`. |
| 4 | "Preserva os testes existentes" | **Parcialmente errado.** `context_broker` passa a ser obrigatório no construtor, então os **dois** testes de `tests/unit/application/test_interpret_audit_command.py` que fazem `InterpretAuditCommandUseCase(interpreter=interpreter)` vão dar `TypeError`. Correção: só adicionar `context_broker=_FakeContextBroker()` nessas duas chamadas, sem mexer em nenhuma asserção. `result is expected` e `assert not hasattr(use_case, "_run_audit_use_case")` continuam valendo sem alteração. Tornar o parâmetro opcional (`= None`) só para não tocar no teste seria gambiarra; não faça. |
| 5 | `InterpretAuditResponse` com 3 campos | Confere. Converter a tupla explicitamente em `from_domain` (`list(...) if not None else None`). |
| 6 | container | Confere. `get_context_broker()` é chamado a cada request, como já acontece em `get_run_audit_use_case()`. |
| 7 | Frontend | Confere, com um detalhe de segurança: **`understoodEnough` também precisa exigir `!isDiscovery()`**. Hoje o guard de `onConfirmClick()` depende só de `understoodEnough`. Se um resultado de descoberta viesse com `entity_type` preenchido e confiança ≥ 0.5, o botão de confirmar seria liberado. |

**Alternativa descartada:** o backend só classifica, e o frontend chama `GET /entity-types` quando recebe `intent=discovery`. O diff no backend seria menor, mas a tela passaria a encadear duas chamadas assíncronas e a resposta à pergunta não ficaria no backend. Não serviria para CLI ou MCP no futuro e fica mais fraco de defender na monografia (a camada de aplicação é quem orquestra SLM e broker).

## 1. Restrições (o agente de código tem que seguir)

1. **TDD estrito:** em cada passo, escrever o teste, ver falhar (`pytest <arquivo>` / `ng test`), implementar, ver passar.
2. **Nenhum comentário novo** em `.py` ou `.ts`: nem docstring, nem `#`, nem `//`, nem `/** */`, nem comentário em `.html`, inclusive nos testes novos. Docstrings antigos ficam como estão. O único lugar com prosa nesta rodada é `command_interpretation.md`, mais o adendo opcional na spec `.md`.
3. Nenhum teste existente pode quebrar. As únicas edições permitidas em testes existentes são as duas chamadas de construtor da seção 2, passo 3 (sem mexer nas asserções).
4. No fim, `pytest` (backend inteiro) e `cd frontend && npx ng test --watch=false` (Karma, `ChromeHeadlessNoSandbox`, já configurado em `karma.conf.js`) precisam passar.
5. Não há Ollama no sandbox. Os testes do adaptador usam `httpx.MockTransport` e **não medem a qualidade real da classificação** pelo Qwen2.5. É uma limitação aceita: registrar no resumo final e não tentar contornar.

## 2. Ordem de execução e arquivos

### Passo 1: domínio (sem teste próprio; é exercitado pelos passos 2 a 4)
`src/auditor/domain/ports/command_interpreter_port.py`
```python
from typing import Literal, Protocol

@dataclass(frozen=True)
class AuditCommandInterpretation:
    entity_type: str | None
    entity_id: str | None
    confidence: float
    raw_command: str
    intent: Literal["audit", "discovery"] = "audit"
    discovered_types: tuple[str, ...] | None = None
    broker_reachable: bool | None = None
```

### Passo 2: adaptador Ollama e prompt
**Teste primeiro:** `tests/unit/infrastructure/llm/test_ollama_command_interpreter.py`, nova classe `TestIntentClassification`, usando o `_client_with_handler` que já existe:

| Teste | Dado | Então |
|---|---|---|
| `test_missing_intent_defaults_to_audit_and_keeps_extracted_type` | JSON `{"entity_type":"Streetlight","entity_id":null,"confidence":0.9}` sem `intent` | `intent == "audit"`, `entity_type == "Streetlight"`, `confidence == 0.9` |
| `test_discovery_intent_is_propagated_without_broker_data` | `{"intent":"discovery","entity_type":null,"entity_id":null,"confidence":0.9}` | `intent == "discovery"`, `confidence == 0.9`, `discovered_types is None`, `broker_reachable is None` (o adaptador nunca preenche esses dois) |
| `test_discovery_intent_discards_any_entity_type_or_id_the_model_returned` | `{"intent":"discovery","entity_type":"Streetlight","entity_id":"urn:x","confidence":0.8}` | `entity_type is None`, `entity_id is None`, `intent == "discovery"` |
| `test_unknown_intent_value_falls_back_to_no_interpretation` | `{"intent":"list_everything","entity_type":"Streetlight","confidence":0.9}` | `intent == "audit"`, `entity_type is None`, `confidence == 0.0`, `raw_command` preservado |
| `test_connection_error_fallback_is_audit_intent` | handler levanta `httpx.ConnectError` | `intent == "audit"` |
| `test_prompt_teaches_the_discovery_intent` | captura o body enviado | `'"intent"' in prompt` e `"discovery" in prompt` (garante que o `.md` foi atualizado) |

**Implementação:** `src/auditor/infrastructure/llm/ollama_command_interpreter.py`
- `from typing import Literal`
- `_InterpretationOutputSchema`: acrescentar `intent: Literal["audit", "discovery"] = "audit"`.
- `_fallback()`: sem mudança (o default do dataclass já dá `"audit"`).
- No `return` final:
```python
is_discovery = parsed.intent == "discovery"
return AuditCommandInterpretation(
    entity_type=None if is_discovery else parsed.entity_type,
    entity_id=None if is_discovery else parsed.entity_id,
    confidence=confidence,
    raw_command=command_text,
    intent=parsed.intent,
)
```
- **Não** adicionar um comentário novo. O comentário que já existe no `except httpx.HTTPError` fica como está.

**Prompt:** `src/auditor/infrastructure/llm/prompts/command_interpretation.md`, substituir inteiro pelo texto da seção 3.

### Passo 3: use case
**Teste primeiro:** `tests/unit/application/test_interpret_audit_command.py`
- Novo fake:
```python
class _FakeContextBroker:
    def __init__(self, types=None, error=None):
        self._types = types or []
        self._error = error
        self.calls: list[Tenant] = []
    async def list_entity_types(self, tenant):
        self.calls.append(tenant)
        if self._error:
            raise self._error
        return self._types
```
- Nas duas chamadas de construtor existentes, adicionar `context_broker=_FakeContextBroker()`. Nada mais muda nesses testes.
- Testes novos:

| Teste | Dado | Então |
|---|---|---|
| `test_audit_intent_never_queries_the_context_broker` | o interpreter devolve a interpretação default (audit, Streetlight, 0.9) | `result is expected`, `broker.calls == []` |
| `test_discovery_intent_returns_types_listed_by_the_context_broker` | o interpreter devolve `intent="discovery"` e o broker tem `["Streetlight","AirQualityObserved"]` | `intent == "discovery"`, `discovered_types == ("Streetlight","AirQualityObserved")`, `broker_reachable is True`, `raw_command` e `confidence` preservados, `broker.calls == [_TENANT]` |
| `test_discovery_intent_with_unreachable_broker_flags_it_without_raising` | o broker levanta `ContextBrokerUnavailableError("Orion inacessivel")` | nenhuma exceção sobe, `discovered_types == ()`, `broker_reachable is False`, `intent == "discovery"` |
| `test_discovery_intent_with_empty_broker_is_reachable_with_no_types` | o broker devolve `[]` | `discovered_types == ()`, `broker_reachable is True` |

**Implementação:** `src/auditor/application/use_cases/interpret_audit_command.py`
```python
from dataclasses import replace
from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.ports.context_broker_port import ContextBrokerPort

class InterpretAuditCommandUseCase:
    def __init__(self, interpreter: CommandInterpreterPort, context_broker: ContextBrokerPort) -> None:
        self._interpreter = interpreter
        self._context_broker = context_broker

    async def execute(self, tenant: Tenant, command_text: str) -> AuditCommandInterpretation:
        interpretation = await self._interpreter.interpret(command_text)
        if interpretation.intent != "discovery":
            return interpretation
        try:
            types = await self._context_broker.list_entity_types(tenant)
        except ContextBrokerUnavailableError:
            return replace(interpretation, discovered_types=(), broker_reachable=False)
        return replace(interpretation, discovered_types=tuple(types), broker_reachable=True)
```

### Passo 4: schema REST e container
**Teste primeiro:** `tests/unit/interfaces/rest/test_audits_router.py`, dentro de `TestInterpretAuditCommand`, usando o `_FakeInterpreterUseCase` que já existe:

| Teste | Dado | Então |
|---|---|---|
| `test_discovery_result_serializes_intent_and_discovered_types` | o fake devolve `intent="discovery", discovered_types=("Streetlight","AirQualityObserved"), broker_reachable=True, entity_type=None, confidence=0.9` | 200, `body["intent"] == "discovery"`, `body["discovered_types"] == ["Streetlight","AirQualityObserved"]`, `body["broker_reachable"] is True`, `fake_use_case.started == []` |
| `test_discovery_with_unreachable_broker_serializes_empty_list_and_flag` | `discovered_types=(), broker_reachable=False` | `body["discovered_types"] == []`, `body["broker_reachable"] is False` |
| `test_audit_result_serializes_audit_intent_and_null_discovery_fields` | a interpretação audit default | `body["intent"] == "audit"`, `body["discovered_types"] is None`, `body["broker_reachable"] is None` |

**Implementação:**
- `src/auditor/interfaces/rest/schemas.py`, em `InterpretAuditResponse`:
```python
intent: Literal["audit", "discovery"]
entity_type: str | None
entity_id: str | None
confidence: float
raw_command: str
discovered_types: list[str] | None
broker_reachable: bool | None
```
  E em `from_domain`: `intent=interpretation.intent`, `discovered_types=list(interpretation.discovered_types) if interpretation.discovered_types is not None else None`, `broker_reachable=interpretation.broker_reachable`.
- `src/auditor/infrastructure/config/container.py`, linha 222:
```python
return InterpretAuditCommandUseCase(
    interpreter=get_command_interpreter(),
    context_broker=get_context_broker(),
)
```
  Não precisa de teste unitário: o router test sobrescreve a factory inteira e um teste de wiring exigiria montar Settings para SaaS e self-hosted. Validar no smoke manual (seção 5).
- `routers/audits.py`: **não muda.**

### Passo 5: frontend
**Teste primeiro:** `frontend/src/app/features/natural-language/natural-language.component.spec.ts`, mesmo padrão dos testes atuais (`component as any`, `httpMock.expectOne(...).flush(...)`, `fixture.detectChanges()`). Nada de comentários `//` nos testes novos.

| `it(...)` | Flush | Então |
|---|---|---|
| `shows the entity types discovered in the broker for a discovery question` | `{intent:'discovery', entity_type:null, entity_id:null, confidence:0.9, raw_command:'quais entidades existem?', discovered_types:['Streetlight','AirQualityObserved'], broker_reachable:true}` | os textos de `.discovery-panel__type` são `['Streetlight','AirQualityObserved']`; `.interpretation-panel--low-confidence` é null |
| `does not offer audit confirmation for a discovery result` | igual ao anterior | `.confirm-button` é null; `component.understoodEnough()` é false; `component.onConfirmClick()` e depois `httpMock.expectNone(`${BASE_URL}/audits`)` |
| `never offers audit confirmation for a discovery result even if a type came back` | `intent:'discovery', entity_type:'Streetlight', confidence:0.9, discovered_types:['Streetlight'], broker_reachable:true` | `understoodEnough()` é false; `.confirm-button` é null; `onConfirmClick()` e depois `expectNone` |
| `warns when the broker is unreachable for a discovery question` | `discovered_types:[], broker_reachable:false` | `.discovery-panel__warning` existe; `.discovery-panel__type` tem 0 elementos; `.confirm-button` é null |
| `says the broker has no entity types when discovery returns an empty list` | `discovered_types:[], broker_reachable:true` | `.discovery-panel__empty` existe; sem `.discovery-panel__warning` |

Os 3 testes atuais fazem flush **sem** `intent` e têm que continuar passando sem edição. Isso prova que `intent` ausente é tratado como audit.

**Implementação:**
- `frontend/src/app/shared/models/command.models.ts`, na interface `InterpretAuditResponse`: `intent: 'audit' | 'discovery';`, `discovered_types: string[] | null;`, `broker_reachable: boolean | null;`.
- `natural-language.component.ts`:
```ts
protected readonly isDiscovery = computed(() => this.interpretation()?.intent === 'discovery');

protected readonly understoodEnough = computed(() => {
  const result = this.interpretation();
  return (
    result !== null &&
    !this.isDiscovery() &&
    result.entity_type !== null &&
    result.confidence >= MIN_CONFIDENCE_TO_CONFIRM
  );
});
```
  Não precisa de JSDoc novo. O JSDoc que já existe acima de `understoodEnough` fica.
- `natural-language.component.html`: dentro de `@case ('interpreted')`, colocar o bloco de descoberta **antes** do `@if (!understoodEnough())`, que vira `@else if`:
```html
@if (isDiscovery()) {
  <div class="interpretation-panel discovery-panel">
    <h2 class="interpretation-panel__title">Tipos de entidade no broker</h2>
    @if (!interpretation()!.broker_reachable) {
      <p class="discovery-panel__warning">
        Não foi possível consultar o broker agora. Verifique a conexão na tela de Configuração e tente novamente.
      </p>
    } @else if ((interpretation()!.discovered_types ?? []).length === 0) {
      <p class="discovery-panel__empty">Nenhum tipo de entidade cadastrado neste broker.</p>
    } @else {
      <ul class="discovery-panel__types">
        @for (type of interpretation()!.discovered_types ?? []; track type) {
          <li class="discovery-panel__type">{{ type }}</li>
        }
      </ul>
      <p class="status-text">Para auditar um deles, peça por exemplo: "audite as entidades {{ interpretation()!.discovered_types![0] }}".</p>
    }
  </div>
} @else if (!understoodEnough()) {
  ...o bloco "Não entendi" atual, sem mudanças...
} @else {
  ...o bloco de confirmação atual, sem mudanças...
}
```
  Opcional, mas recomendado: acrescentar ao subtítulo `.page-subtitle` "… ou pergunte o que existe no broker (ex.: "quais entidades existem?")", e na mensagem de "Não entendi" uma frase com essa mesma dica. Nenhum teste verifica esses textos.
- `natural-language.component.scss`: `.discovery-panel__types { margin: 0 0 var(--space-3); padding-left: var(--space-4); }`, `.discovery-panel__type { font-family: monospace; }`, `.discovery-panel__warning { color: var(--color-warning); }`, `.discovery-panel__empty { color: var(--color-text-secondary); }`. O token `--color-warning` já existe em `frontend/src/styles.scss:19`.
- `natural-language-api.service.ts`: **não muda.**

### Passo 6 (opcional, só `.md`): adendo em `.cursor/specs/fase8.spec.md` §0.3
Descrever `intent`, `discovered_types` e `broker_reachable`, e registrar que a descoberta é leitura. Com `intent == "audit"`, o `context_broker` nunca é tocado, e o use case continua sem chamar `RunAuditUseCase`.

## 3. Texto novo de `command_interpretation.md`

```markdown
# Interpretação de comando em linguagem natural

Você interpreta uma frase em português, escrita livremente por um operador, sobre entidades
FIWARE NGSI-v2 num Context Broker (Orion). Você **nunca** executa nada — apenas classifica e
interpreta, para que a interface mostre o resultado ao usuário antes de qualquer ação.

## 1. Classifique a intenção (`intent`)

- `"audit"` — o usuário pede para **auditar, verificar, validar ou checar** entidades
  (ex.: "audite os postes de luz", "verifique a entidade urn:ngsi-ld:Streetlight:001",
  "checar conformidade dos sensores de qualidade do ar"). Este é o caso padrão: na dúvida
  entre as duas intenções, use `"audit"`.
- `"discovery"` — o usuário **pergunta o que existe** no broker, sem pedir auditoria
  (ex.: "quais entidades existem no broker?", "quais tipos estão cadastrados?",
  "o que tem nesse broker?", "liste os tipos de entidade disponíveis").

Use exatamente um destes dois valores, em minúsculas: `"audit"` ou `"discovery"`.

## 2. Se `intent` for `"audit"`, identifique, se possível:

- `entity_type`: um tipo de entidade NGSI plausível (ex.: "Streetlight",
  "AirQualityObserved", "WeatherObserved") — em `PascalCase`, como os Smart Data Models
  oficiais nomeiam seus tipos. Se o comando não permitir identificar um tipo com
  confiança razoável, responda `null` — nunca invente um tipo plausível-mas-errado.
- `entity_id`: um identificador NGSI específico, só se o comando citar um explicitamente
  (ex.: "audite a entidade urn:ngsi-ld:Streetlight:001"). Na maioria dos comandos isso
  será `null` — o usuário normalmente quer auditar por tipo, não uma entidade específica.

## 3. Se `intent` for `"discovery"`:

`entity_type` e `entity_id` são sempre `null` — a pergunta é sobre o que existe no broker,
não sobre um tipo específico. Quem responde com a lista real de tipos é o sistema, não você:
nunca liste nem invente tipos na resposta.

## 4. Em ambos os casos, `confidence`

Um número entre 0.0 e 1.0 refletindo o quão certo você está da interpretação como um todo.
Frases vagas ou ambíguas devem receber confiança baixa (< 0.5).

## Formato da resposta

Responda **apenas** com um objeto JSON, sem nenhum texto fora dele, sempre com as quatro
chaves `intent`, `entity_type`, `entity_id`, `confidence`.

Exemplos:

- "audite os sensores de qualidade do ar"
  `{"intent": "audit", "entity_type": "AirQualityObserved", "entity_id": null, "confidence": 0.9}`
- "verifique a entidade urn:ngsi-ld:Streetlight:001"
  `{"intent": "audit", "entity_type": "Streetlight", "entity_id": "urn:ngsi-ld:Streetlight:001", "confidence": 0.95}`
- "faz uma coisa aí"
  `{"intent": "audit", "entity_type": null, "entity_id": null, "confidence": 0.1}`
- "quais entidades existem no broker?"
  `{"intent": "discovery", "entity_type": null, "entity_id": null, "confidence": 0.95}`
- "o que tem cadastrado nesse broker?"
  `{"intent": "discovery", "entity_type": null, "entity_id": null, "confidence": 0.9}`

## Comando do usuário

%%COMMAND_TEXT%%
```

Chaves e JSON no template são seguros: `_build_prompt` usa `str.replace` e não `str.format`.

## 4. Riscos e efeitos colaterais

1. **Não há outros consumidores.** `CommandInterpreterPort`, `AuditCommandInterpretation` e `InterpretAuditCommandUseCase` só aparecem no port, no adaptador, no use case, em `schemas.py`, `routers/audits.py` e `container.py`. Não existe CLI, MCP ou worker usando esses tipos.
2. **Integração, e2e e golden não são afetados.** `tests/integration/test_run_audit_e2e.py` e `tests/golden/` (só `OllamaAnalyzer`) não usam o interpretador. Não há golden test do `OllamaCommandInterpreter`.
3. **Template com campos `null`:** respostas antigas ou fakes sem `intent` (os 3 specs atuais) caem no fluxo audit, porque `undefined === 'discovery'` é falso. `discovered_types` null é protegido com `?? []`. Se `broker_reachable` vier null em discovery (não acontece pelo backend), o aviso aparece, o que é fail-safe.
4. **SaaS sem conta cadastrada:** em discovery, `TenantRoutedContextBroker` levanta `TenantBrokerNotConfiguredError`, que o handler global transforma em **401 "faça login novamente"**. É o mesmo comportamento do `/entity-types` e é intencional. Em intent audit isso nunca ocorre, porque o broker não é chamado.
5. **Classificação errada pelo SLM:** se um comando de auditoria vier como discovery, o fluxo de confirmação some, mas a tela mostra os tipos e a dica "audite as entidades X", e o usuário reformula. É o erro menos grave, porque nunca dispara ação. O erro inverso (pergunta classificada como audit) cai no "Não entendi", que é o comportamento de hoje. O prompt manda "na dúvida, audit". Isso não é testável sem Ollama e fica registrado como limitação.
6. **Maiúsculas:** `"Discovery"` ou `"AUDIT"` falham no `Literal` e caem em fallback total. Foi aceito para manter o contrato simples; o prompt exige minúsculas. Se aparecer na prática, a correção é um `field_validator` com `.lower()`.
7. **Docstrings antigos ficam desatualizados:** o de `interpret_audit_command.py` diz que "a interpretacao em si nao filtre nada por tenant hoje", o que deixa de ser verdade para discovery. A regra só proíbe adicionar comentários. **Remover** essa frase é permitido; decida no momento da implementação. Não reescrever o texto, só remover o que ficou falso.
8. **Custo:** `get_context_broker()` passa a ser construído a cada `POST /audits/interpret`, inclusive em audit. É barato, sem I/O no construtor, e é o mesmo padrão de `get_run_audit_use_case()`.

## 5. Checagem final

- `pytest` (backend inteiro) e `cd frontend && npx ng test --watch=false` passando.
- Verificar no diff que não há `#`, `"""`, `//` ou `/**` adicionados em `.py` e `.ts`.
- Smoke manual, fora do sandbox, com Ollama e Orion no ar: "quais entidades existem no broker?" mostra a lista; "audite os postes de luz" mantém o fluxo atual; derrubar o Orion e repetir a pergunta mostra o aviso.

### Arquivos críticos para a implementação
- `src/auditor/application/use_cases/interpret_audit_command.py`
- `src/auditor/infrastructure/llm/ollama_command_interpreter.py`
- `src/auditor/infrastructure/llm/prompts/command_interpretation.md`
- `src/auditor/interfaces/rest/schemas.py`
- `frontend/src/app/features/natural-language/natural-language.component.html`

Outros arquivos que mudam: `src/auditor/domain/ports/command_interpreter_port.py`, `src/auditor/infrastructure/config/container.py`, `frontend/src/app/shared/models/command.models.ts`, `frontend/src/app/features/natural-language/natural-language.component.ts`, `.scss` e `.spec.ts`. Testes: `tests/unit/application/test_interpret_audit_command.py`, `tests/unit/infrastructure/llm/test_ollama_command_interpreter.py` e `tests/unit/interfaces/rest/test_audits_router.py`.
