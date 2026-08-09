# Architecture Decision Records — DKRT

Este diretório registra as decisões arquiteturais do projeto, uma por arquivo, na ordem em que foram tomadas.

## Por que isso existe

Um ADR não documenta *o que* o sistema faz (isso é o README/documentação técnica) — documenta *por que* uma decisão foi tomada em vez de outra, quais alternativas foram avaliadas, e quais consequências (boas e ruins) foram aceitas. É o material mais direto para justificar escolhas de projeto numa defesa de TCC ou na monografia.

## Convenções

- Um arquivo por decisão: `000X-titulo-curto.md`, numeração sequencial.
- Um ADR **nunca é editado** depois de `Status: Aceito`. Se a decisão mudar, cria-se um novo ADR com `Status: Substituído por ADR-000Y`, e o antigo recebe `Status: Substituído por ADR-000Z`.
- Cada ADR segue o mesmo molde (ver `TEMPLATE.md`).

## Índice

| ADR | Título | Status |
|---|---|---|
| [0001](0001-unificacao-arquitetura-agentes.md) | Unificação da arquitetura de agentes | Aceito |
| [0002](0002-loop-execucao-verificacao-correcao.md) | Loop de execução com verificação determinística e correção | Aceito |
| [0003](0003-quantumleap-em-vez-de-sth-comet.md) | QuantumLeap como componente de histórico | Aceito |
| [0004](0004-escopo-cobertura-fiware.md) | Redefinição do escopo de cobertura FIWARE | Aceito |

## Como escrever o próximo

Toda vez que você (ou o grupo) tomar uma decisão técnica que poderia razoavelmente ter ido para outro lado — escolha de biblioteca, padrão de arquitetura, formato de dado, trade-off de desempenho vs. simplicidade — vale um ADR. Copie `TEMPLATE.md`, numere sequencialmente, preencha os 4 campos, e adicione a linha no índice acima.

Sinais de que uma decisão merece ADR: você discutiu mais de uma opção antes de decidir; a decisão é difícil de reverter depois; alguém no futuro (inclusive você, em 6 meses) provavelmente vai perguntar "por que fizemos assim?".