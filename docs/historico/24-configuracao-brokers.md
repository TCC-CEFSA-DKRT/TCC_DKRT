# 24 — Tela de configuração dos brokers

## 2026-11-15 — Teste de conexão, validação e broker local × nuvem (Tainara)

**Contexto:** a tela de Configuração (modo self-hosted) só salvava URL, Fiware-Service e Fiware-ServicePath e, depois de salvar, chamava `GET /entity-types` para avisar se o broker respondia. Dava para salvar um broker que não funcionava sem perceber, os erros não diziam o motivo e não havia como informar uma chave de acesso.

**O que mudou:**
- Backend: `POST /config/test` testa os valores digitados **sem salvar** e devolve `status` (`ok`, `invalid_url`, `unreachable`, `timeout`, `unauthorized`, `unexpected_response`), `entity_types_count` e `http_status`.
- `PUT /config` agora testa a conexão antes de salvar. Se falhar, responde **409** com o motivo e não grava nada; só grava um broker que falhou com `save_without_connection: true`, que a tela envia depois que o usuário clica em "Salvar mesmo assim".
- `broker_kind` (`local` ou `cloud`) e `broker_api_key` no `PUT` e no teste. `GET /config` devolve `broker_kind`, `has_api_key` (nunca a chave) e `default_local_broker_url` (vem de `FIWARE_BROKER_URL`).
- Domínio: `BrokerConnectionStatus`/`BrokerConnectionCheck` (`domain/value_objects/broker_connection.py`) e a porta `BrokerConnectionTesterPort`; infraestrutura: `OrionConnectionTester` (`infrastructure/context_broker/orion_connection_tester.py`), registrado em `container.py::get_broker_connection_tester`.
- Frontend: escolha "Instância Docker local" × "Broker em nuvem", botão "Testar conexão", validação de cada campo com mensagem ao lado, campo de chave de acesso (só para nuvem), aviso explícito antes de salvar um broker que falhou. As chamadas HTTP saíram do componente para `config-api.service.ts`; regras de validação em `config-validation.ts`; textos e padrões em `config.constants.ts`.

**Por quê / decisões:**
- O bloqueio de salvar está no backend (409), não só na tela: o critério de aceite diz que não é possível salvar uma configuração que falha no teste sem aviso explícito, e isso precisa valer para qualquer cliente da API.
- O teste chama `GET /v2/types` do Orion, a mesma chamada da descoberta de tipos: confirma URL, rede, credencial e que o endereço é mesmo um Orion, e devolve quantos tipos existem (mostrado na mensagem de sucesso).
- Tempo limite do teste: 5 s (`CONNECTION_TEST_TIMEOUT_SECONDS`, no backend e no texto da tela). As auditorias continuam com 30 s (`OrionAdapter`).
- Broker em nuvem exige `https://` (validação na tela e no `BrokerConfigRequest`), porque a chave de acesso vai no cabeçalho `Authorization: Bearer`.
- O tipo do broker não ganhou coluna no banco: `GET /config` deduz `cloud` quando a URL é `https://` ou há chave salva, e `local` nos outros casos. Evita migration para uma informação que só serve para a tela.
- Chave em branco no modo nuvem mantém a chave salva; escolher "Docker local" remove a chave. A API nunca devolve a chave, só `has_api_key`.
- Cada mensagem de erro diz o que conferir (URL, porta, `docker compose ps`, chave). O resultado de um teste some assim que algum valor muda, para não mostrar "funcionando" de uma configuração que não foi testada.

**Testes (cuidado pedido pelo Diego na revisão da #61):**
- Os testes estão organizados pelo comportamento da tela e da API ("testar a conexão antes de salvar", "salvar"), não pelo número da issue, e cada nome diz o resultado esperado.
- Cada mensagem de erro tem o próprio teste, e os casos de erro (porta fechada, broker que não responde, 401/403, 404, resposta que não é do Orion, API do auditor fora do ar) têm o mesmo peso do caminho feliz.
- `test_orion_connection_tester.py` usa um servidor HTTP de verdade em `127.0.0.1` e uma porta realmente fechada, em vez de simular a exceção do `httpx`: assim o teste prova que a falha de rede real cai na mensagem certa, e não só que o código trata a exceção que o próprio teste lançou.
- `tests/integration/context_broker/test_orion_connection_tester_integration.py` testa contra o Orion do docker compose; `tests/integration/test_config_broker_e2e.py` passa pela API inteira (`PUT /config` → Postgres → `GET /config`) e prova o critério de aceite: com o broker fora do ar nada é gravado, e só grava com a confirmação explícita.

**Armadilhas e pontos de atenção:**
- Os dois testes de integração precisam do Orion do `docker compose up -d` (porta 1026, `ORION_MULTI_SERVICE=TRUE`) e do Docker para o Postgres descartável (testcontainers). No CI rodam no job "Integração (PostgreSQL, Orion e migrações)". Usam os serviços `auditor_config_test` e `auditor_config_e2e`, para não contar as entidades de demonstração.
- `orion_connection_tester.py::_is_valid_broker_url` — o `httpx.URL` aceita host com espaço (vira `%20`) e mandaria a requisição; por isso a URL com qualquer espaço é recusada antes.
- `orion_adapter.py::orion_headers` — cabeçalhos do Orion (`Fiware-Service`, `Fiware-ServicePath`, `Authorization`) extraídos para uma função, usada pelo `OrionAdapter` e pelo teste de conexão, para os dois mandarem exatamente os mesmos cabeçalhos.
- `routers/config.py::put_config` — com `save_without_connection: true` o teste não roda e a resposta vem com `connection: null`; a tela usa isso para mostrar "Configuração salva sem conexão confirmada".
- `tests/qualidade/test_bb_04_api_inputs.py::_cliente` e `tests/unit/interfaces/rest/test_config_router.py::_client` — sobrescrevem `get_broker_connection_tester` com um broker falso, senão o `PUT /config` dos testes tentaria acessar a rede.
- `config.component.ts::connection` — o resultado do teste fica guardado junto com uma "chave" dos valores testados (`config-connection.ts::connectionValuesKey`); se a chave muda, o resultado deixa de aparecer.

**Pendências:**
- Modo SaaS: a configuração do broker continua sendo feita fora da tela (cadastro do tenant); `POST /config/test` só existe no modo self-hosted, como o resto de `/config`.

**Referências:** issue #24, ADR-0019 (instalação self-hosted), `docs/historico/71-temas-e-interfaces.md` (branch base).
