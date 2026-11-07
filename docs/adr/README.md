# Architecture Decision Records — DKRT

Este diretório registra as decisões arquiteturais do projeto, uma por arquivo, na ordem em que foram tomadas.

## Por que isso existe

Um ADR não documenta *o que* o sistema faz (isso é o README/documentação técnica) — documenta *por que* uma decisão foi tomada em vez de outra, quais alternativas foram avaliadas, e quais consequências (boas e ruins) foram aceitas. É o material mais direto para justificar escolhas de projeto numa defesa de TCC ou na monografia.

## Convenções

- Um arquivo por decisão: `adr-00XX.md`, numeração sequencial com dois dígitos (ex.: `adr-0007.md`).
- Um ADR **nunca é editado** depois de `Status: Aceito`. Se a decisão mudar, cria-se um novo ADR com `Status: Substituído por ADR-000Y`, e o antigo recebe `Status: Substituído por ADR-000Z`.
- Cada ADR segue o mesmo molde (ver `template.md`).

As ADRs 0000 a 0012 documentam a fase multiagente inicial do projeto, substituída pela reescrita registrada em `docs/plano_refatoracao_v3.md` (ver também `docs/legacy/README.md`). Foram mantidas como histórico de raciocínio — valorizado numa defesa de TCC — mas **não descrevem a arquitetura atual**. A partir da ADR-0013 as decisões referem-se ao sistema vigente.

## Índice

| ADR | Título | Status |
|---|---|---|
| [0000](adr-0000.md) | Orquestração determinística com SLM classificador, em vez de agente aberto (tool-use) com RAG/fine-tuning | Aceito |
| [0001](adr-0001.md) | Unificação da arquitetura de agentes | Aceito |
| [0002](adr-0002.md) | Loop de execução com verificação determinística e correção | Aceito |
| [0003](adr-0003.md) | QuantumLeap como componente de persistência histórica | Aceito |
| [0004](adr-0004.md) | Redefinição do escopo de cobertura FIWARE | Aceito |
| [0005](adr-0005.md) | O que entra no verify | Proposto \| Aceito \| Substituído por ADR-000Y |
| [0006](adr-0006.md) | Convenção de nomenclatura — Handler vs. Dispatcher | Aceito |
| [0007](adr-0007.md) | RouteAgent vira RouteDispatcher (fallback determinístico) | Aceito |
| [0008](adr-0008.md) | SubscribeAgent vira SubscribeHandler, implementação completada no Bloco 5 | Aceito |
| [0009](adr-0009.md) | AnalyzeAgent vira AnalyzeHandler, escopo restrito à formatação de resultado já verificado | Aceito |
| [0010](adr-0010.md) | Coexistência de STH-Comet (legado) e QuantumLeap (novo) para dados históricos | Aceito |
| 0011 | — | *(número não utilizado — sem arquivo correspondente)* |
| [0012](adr-0012.md) | IoT Agent MQTT como sétima operação do vocabulário (iot_provision) | Aceito |
| [0013](adr-0013.md) | Ollama em EC2 (não Bedrock) como SLM de produção | Aceito (instância revista pela 0015) |
| [0014](adr-0014.md) | Nível 2 (SLM) passa a analisar toda entidade com schema resolvido | Aceito |
| [0015](adr-0015.md) | Ollama em instância com GPU para o SLM de produção | Aceito |
| [0016](adr-0016.md) | Servidor MCP como adaptador de entrada para expor a auditoria a clientes de IA | Aceito |
| [0017](adr-0017.md) | API e worker de produção migram de EC2 para Lambda (imagem de contêiner) atrás de um ALB, com CloudFront/S3, Parameter Store e VPC endpoints | Aceito |
| [0018](adr-0018.md) | AWS Academy Learner Lab descontinuada — `environments/academy` renomeado para `environments/homolog` | Parcialmente substituído por ADR-0021 |
| [0019](adr-0019.md) | Dois modos de implantação (SaaS multi-tenant + self-hosted no ambiente do produtor) | Proposto |
| [0020](adr-0020.md) | Sessão por cookie httpOnly (SaaS) + gate de Configuração (self-hosted) + `/session` em runtime no lugar da flag de build | Proposto |
| [0021](adr-0021.md) | Três ambientes AWS (dev em EC2, homologação e produção em Lambda), pipeline por GitHub Actions com OIDC e build único promovido | Aceito |

## Como escrever o próximo

Toda vez que você (ou o grupo) tomar uma decisão técnica que poderia razoavelmente ter ido para outro lado — escolha de biblioteca, padrão de arquitetura, formato de dado, trade-off de desempenho vs. simplicidade — vale um ADR. Copie `template.md`, numere sequencialmente, preencha os 4 campos, e adicione a linha no índice acima.

Sinais de que uma decisão merece ADR: você discutiu mais de uma opção antes de decidir; a decisão é difícil de reverter depois; alguém no futuro (inclusive você, em 6 meses) provavelmente vai perguntar "por que fizemos assim?".
