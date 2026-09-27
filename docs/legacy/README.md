# Documentação legada — fase multiagente (pré-refatoração)

Este diretório reúne documentação da primeira iteração do projeto: um sistema multiagente
que operava o Orion Context Broker via comandos em linguagem natural, orquestrador central,
handlers especializados (`RouteDispatcher`, `ChatEngine`, `AnalyzeHandler`, etc.) e um RAG
próprio. Essa arquitetura foi **descartada e reescrita do zero** — ver `docs/plano_refatoracao_v3.md`
(Parte IV) para o registro da decisão.

Preservado aqui por valor histórico para a monografia (mesmo raciocínio das ADRs 0000-0012,
ver `docs/adr/README.md`) — **nada neste diretório descreve o sistema atual.**

Para a arquitetura, escopo e especificações vigentes: `.cursor/specs/fase1.spec.md` a
`fase10.spec.md`, e `docs/plano_refatoracao_v3.md`.

## Conteúdo

- `fases/` — as 12 fases do plano multiagente original (substituídas por `.cursor/specs/`)
- `analizy/analise.md` — análise técnica do sistema multiagente antigo
- `base-secao8-implicacoes-dkrt.md` — seção extraída de `docs/base/fiware-e-orion-context-broker.md`
  (o restante daquele arquivo continua válido como referência genérica de FIWARE/NGSI-v2)
- `readme-raiz-antigo-dkrt.md` — íntegra do `README.md` da raiz antes da reescrita (o `README.md`
  atual já reflete a arquitetura vigente; nada de novo precisou ser extraído dele, só arquivado)
