# Suporte a NGSI-LD, selecionável por broker/tenant

## 2026-11-20 — CI verde: paginação sem limite, comentário novo e falso positivo do gitleaks (Diego)

**Contexto:** três falhas no CI deste PR, sem relação com NGSI-LD em si — a suíte (`tests/qualidade/test_bb_04_api_inputs.py::test_listar_execucoes[CT-PAG-09]`), o verificador de comentários e o `gitleaks`.

**O que mudou:**
- `interfaces/rest/routers/audits.py::list_audits` — `page`/`page_size` passaram de `int` puro pra `Query(ge=1)`/`Query(ge=1, le=100)`. Sem isso, `GET /audits?page_size=101` (e `page=0`, `page=-1`, `page_size=0`, `page_size=-5`, `page_size=1000000`) devolvia 200 em vez do 422 que o contrato de paginação (RF-05) já previa nos casos de teste.
- `tests/qualidade/test_bb_04_api_inputs.py::_PG` — removido o `defeito="D-01"` dos 6 casos (`CT-PAG-02/03/06/07/09/10`) agora que o limite é aplicado; esses casos eram `xfail(strict=True)` de propósito (ver `docs/qualidade/README.md`), então continuar validando sem tirar a marca faria o CI falhar por XPASS estrito.
- Comentário novo em `test_bb_04_api_inputs.py:197` (explicando o contrato de paginação) removido; o contexto foi pra esta entrada em vez de ficar no código, como manda o `AGENTS.md`.
- `.gitleaks.toml` novo na raiz, com `[extend] useDefault = true` e um `[allowlist].paths` cobrindo `tests/qualidade/test_bb_04_api_inputs.py` — esse arquivo só tem credenciais de fixture (`senha-correta-123`, `user@example.com`) pra testar `POST /auth/login`, nunca segredo real; o `security.yml` já passava `--config /repo/.gitleaks.toml` implicitamente por auto-detecção, mas passou a receber o flag explícito pra não depender disso.

**Por quê / decisões:**
- Path-allowlist no arquivo inteiro em vez de regex por segredo: é o único arquivo de teste com esse tipo de dado, e qualquer senha/e-mail de fixture nova ali seria o mesmo tipo de falso positivo — regra mais específica só adicionaria manutenção sem reduzir risco real (não é um arquivo de produção).
- Não toquei `docs/qualidade/resultados/{matriz_rastreabilidade.csv,casos_de_teste.json,junit.xml}` nem o `.docx`/`.pdf` do relatório — são artefatos gerados por `scripts/qualidade/matriz_rastreabilidade.py` a partir de uma execução da suíte, não leio à mão; regenerar fica pendente.

**Armadilhas e pontos de atenção:**
- `tests/unit/infrastructure/config/test_context_broker_factory.py` e `test_tenant_account_repository_factory.py` falham localmente (`DID NOT RAISE RuntimeError`) mesmo em `main`/sem nenhuma mudança deste PR — algo no ambiente local (provavelmente `BROKER_API_KEY_ENCRYPTION_KEYS` já setada na env do shell) vaza pro `monkeypatch.delenv`. Confirmado com `git stash` que o mesmo falha sem as mudanças daqui; não é regressão deste PR, nem reproduz no CI (que começou limpo nesse ponto).

**Pendências:**
- Regenerar `docs/qualidade/resultados/*` e o relatório (`.docx`/`.pdf`) pra refletir que D-01 foi corrigido (6 casos saem de "defeito conhecido" pra "conforme").
- Mesma pendência de renormalização CRLF→LF já registrada na entrada anterior deste arquivo continua aberta.

**Referências:** PR atual (continuação de c3a44a35/23408896/a1722abf), `docs/qualidade/README.md` (seção "Defeitos conhecidos").

## 2026-11-20 — OrionLdAdapter convivendo com o OrionAdapter (ADR-0023) (Diego)

**Contexto:** o sistema só falava NGSI-v2 com o Orion (`OrionAdapter` fixo em todo lugar que instanciava um `ContextBrokerPort`). Era pra atender as duas estruturas (NGSI-v2 e NGSI-LD), com o cliente escolhendo qual broker usa em cada caso — não uma troca total de protocolo.

**O que mudou:**
- `OrionLdAdapter` novo (`infrastructure/context_broker/orion_ld_adapter.py`), implementando o mesmo `ContextBrokerPort` contra `/ngsi-ld/v1/entities` e `/ngsi-ld/v1/types`.
- `adapter_factory.build_orion_adapter(ngsi_version, base_url, client, api_key=None)` é o único ponto que decide entre `OrionAdapter` (v2) e `OrionLdAdapter` (ld) — `TenantRoutedContextBroker`, `SelfHostedContextBroker` e `container.py::get_context_broker` chamam essa função em vez de instanciar o adapter concreto direto.
- Seleção por configuração, não global: `Settings.fiware_ngsi_version` (`FIWARE_NGSI_VERSION=v2|ld`, usado quando não há conta salva no modo selfhosted) e coluna `tenant_accounts.ngsi_version` (migração `e56fc59d8c7b`, `server_default='v2'`) por conta salva. Exposto em `GET/PUT /config` (`BrokerConfigRequest`/`BrokerConfigResponse.ngsi_version`) e em `audit tenant-register --ngsi-version {v2,ld}`.
- `BrokerConnectionTesterPort.check()` ganhou o parâmetro `ngsi_version` (default `"v2"`); `OrionConnectionTester` testa `/ngsi-ld/v1/types` com os cabeçalhos LD quando a conta é `ld`.
- ADR-0023 documenta a decisão completa.

**Por quê / decisões:**
- `NgsiV2Mapper`, `StructuralValidator` e `RunAuditUseCase` não mudaram nada: `OrionLdAdapter` pede `Accept: application/json` (representação normalizada, sem `@context` inline) em vez de `application/ld+json`, o que deixa o corpo de cada entidade LD estruturalmente parecido com NGSI-v2 (`{"atributo": {"type": ..., "value": ...}}`) — o mapper só exige a chave `"value"`, não olha o que `"type"` diz.
- A única forma de atributo LD sem equivalente direto em v2 é `Relationship` (usa `"object"` em vez de `"value"`). `orion_ld_adapter.py::_normalize_relationships` copia `object` → `value` na borda, antes de a entidade chegar no `StructuralValidator`, para o Nível 1 nunca precisar saber qual protocolo buscou aquela entidade.
- `tenant_account_repository.py::TenantAccount.ngsi_version` foi colocado como o **último** campo do dataclass, com `= "v2"` como default — não entre `broker_api_key` e `login_email` (onde cairia naturalmente por proximidade semântica) — porque `tests/qualidade/test_bb_04_api_inputs.py` já construía `TenantAccount(...)` com 7 argumentos posicionais na ordem antiga; um campo sem default inserido no meio quebraria essa chamada silenciosamente (o e-mail cairia no slot errado) em vez de dar erro claro.
- `update_broker()`/`replace_tenant()` recebem `ngsi_version: str | None = None`: `None` preserva o que já estava salvo (troca de URL/host não é motivo pra resetar v2/ld sozinha); só troca quando quem chama informa `v2`/`ld` explicitamente.
- Deliberadamente fora do escopo desta entrega: o seletor v2/ld na tela Angular de configuração do broker self-hosted (a API já aceita e devolve `ngsi_version`; falta o componente usar isso) — ADR-0023 registra isso nas consequências aceitas.

**Armadilhas e pontos de atenção:**
- `interfaces/rest/routers/config.py::get_config` — `account.ngsi_version` vem do banco como `str`; o `cast(NgsiVersion, ...)` ali é só pra satisfazer o mypy (`BrokerConfigResponse.ngsi_version` é `Literal["v2","ld"]`), a invariante real é garantida na escrita (CLI valida `--ngsi-version`, `BrokerConfigRequest` valida via `Literal` no Pydantic).
- `tests/unit/interfaces/rest/test_config_router.py::_FakeTester.check` e `_FakeAccounts.replace_tenant`, `tests/qualidade/test_bb_04_api_inputs.py::_BrokerAlcancavel.check`/`_Accounts.create`/`.replace_tenant`, `tests/unit/interfaces/aws_lambda/test_admin_handler.py` e `tests/unit/interfaces/cli/test_cli.py` (dublês de `TenantAccountRepository.create`) — todos precisaram aceitar o parâmetro novo (`ngsi_version`/`**kwargs`); sem isso o `PUT /config`, o teste de conexão e o `tenant-register` dos testes quebravam com `TypeError` ou, pior, com `assert 500 == 200` sem dizer o motivo.
- `src/auditor/infrastructure/config/container.py`, `settings.py`, `persistence/tables.py`, `interfaces/cli/main.py`, `tests/qualidade/test_bb_04_api_inputs.py` e `tests/unit/interfaces/cli/test_cli.py` já estavam salvos com CRLF em `main`, apesar de `.gitattributes` dizer `eol=lf` para todo `*.py` (`* text=auto eol=lf`) — débito anterior a esta entrega, não causado por ela. Qualquer edição nesses arquivos por qualquer ferramenta que escreva `\n` (como esta) faz o `git add`/commit normalizar pra LF (o próprio `.gitattributes` força isso na hora de indexar, não tem como escapar disso editando o arquivo), e isso faz o diff contra `origin/main` mostrar o arquivo inteiro como alterado — o que por sua vez fez tanto `ci-comentarios.yml` (sinaliza comentário antigo como "novo") quanto o `gitleaks` do `security.yml` (atribui um segredo de teste pré-existente, tipo a senha de fixture `"senha-correta-123"` em `test_bb_04_api_inputs.py`, ao commit que só re-normalizou a linha) dispararem falso positivo. Renormalizar esses 6 arquivos pra LF numa `main` própria (`git add --renormalize`) resolveria na raiz; não foi feito aqui por estar fora do escopo de "implementar NGSI-LD".

## 2026-11-20 — Seletor v2/ld na tela de Configuração (Diego)

**Contexto:** a API já aceitava e devolvia `ngsi_version`, mas a tela Angular de configuração do broker self-hosted não tinha como escolher a estrutura — sempre mandava `v2` implícito, e o rótulo do painel de login dizia só "NGSI-v2 · Smart Data Models".

**O que mudou:**
- Novo fieldset "Qual é a estrutura dos dados?" em `config.component.html`, com os mesmos radio buttons de `config-kind` (reaproveitado o CSS, sem classe nova), logo abaixo do "Onde está o broker?".
- `NgsiVersion` (`shared/interfaces/config.interface.ts`), `ngsi_version` em `BrokerTargetRequest`/`BrokerConfigResponse`; `ngsiVersion` em `ConfigFormValues`; `NGSI_VERSION_OPTIONS` (`config.constants.ts`, mesmo formato de `BrokerKindOption`); `ConfigComponent.setNgsiVersion()` espelha `setKind()`.
- `config-connection.ts::connectionValuesKey` passou a incluir `ngsiVersion` — trocar a estrutura invalida um teste de conexão já feito, do mesmo jeito que trocar a URL já invalidava.
- `split-panel.component.ts`: rótulo passou a "NGSI-v2 e NGSI-LD · Smart Data Models".

**Armadilhas:**
- Sem Chrome/Chromium nem o binário Linux do esbuild neste ambiente de desenvolvimento (node_modules instalado no Windows do Diego) — não rodou `ng test`/`ng build` aqui. Verificado só com `tsc --noEmit` (`tsconfig.app.json` e `tsconfig.spec.json`, os dois sem erro) — o CI ("ng test e ng build", ambiente Linux limpo) é quem valida de fato.
- `config.component.spec.ts::` o teste de `POST /config/test` comparava o corpo da requisição com `toEqual` (objeto exato); precisou somar `ngsi_version: 'v2'` no objeto esperado, senão quebra mesmo sem nada de errado no código.

**Pendências:**
- `scripts/ci/check_no_comments.py` ganhou `--ignore-cr-at-eol` no `git diff` interno (uma linha) porque, sem isso, qualquer PR que toque `container.py`/`tables.py`/`cli/main.py`/`test_bb_04_api_inputs.py`/`test_cli.py` reprova o CI "Comentários" por reportar comentário antigo como novo (mesma causa do parágrafo acima) — a correção de raiz (renormalizar esses 6 arquivos em `main`) continua pendente, mas deixou de bloquear PRs enquanto isso não acontece.
- Seletor v2/ld na tela Angular de configuração do broker self-hosted (frontend não tocado nesta entrega).
- Testes de integração reais (`tests/integration/persistence/test_tenant_account_repository.py`, casos novos de `ngsi_version`) só verificados por sintaxe — dependem de Postgres real via testcontainers, não disponível neste ambiente.
- Renormalização de fim-de-linha (CRLF→LF) de `container.py`, `settings.py`, `tables.py`, `cli/main.py`, `test_bb_04_api_inputs.py` e `test_cli.py` em `main`, pra esses arquivos pararem de gerar diff cheio/falso-positivo em qualquer PR futuro que os toque.

**Referências:** ADR-0023 (`docs/adr/adr-0023.md`), ADR-0019 (instalação self-hosted, mesmo modelo de conta por tenant), ADR-0017 (fila/job queue, mesmo padrão de "fábrica decide a implementação por configuração" usado aqui em `adapter_factory.py`).
