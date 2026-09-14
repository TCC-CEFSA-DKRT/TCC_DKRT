# Data space FIWARE — demo didática (2 produtores + 1 consumidor)

## O que isso é (e o que não é)

Este pacote implementa os 5 conceitos de um data space — **catálogo, negociação, transferência,
recebimento e aplicação de política de uso** — usando um conector próprio, bem mais simples que o
FDC (FIWARE Data Space Connector) ou o TRUE Connector reais. A simplificação é intencional, para
focar a aula no *conceito* de soberania, não na operação de um Helm chart com EDC, DAPS e Vault.

O que foi abstraído e por quê:

- **Sem Keyrock/Wilma/AuthzForce**: cada produtor tem só Orion + conector. Em produção esses GEs
  protegeriam o Orion *internamente*; aqui o foco é a borda do data space, não o intra-domínio.
- **Trust anchor simplificado**: as três pontas compartilham um token fixo (`SHARED_TOKEN`) em vez
  de mTLS com certificados emitidos por um DAPS/Gaia-X Clearing House. Mesma ideia (só conector
  confiável recebe resposta), implementação muito mais simples de explicar e rodar.
- **Protocolo de negociação simplificado**: não é o Dataspace Protocol (DSP) real do IDSA/EDC, é um
  request/response direto que produz o mesmo artefato conceitual — um *agreement* com política
  anexada (finalidade, TTL, permissão de redistribuição).
- **Orion clássico (NGSI-v2)**, não Orion-LD, para ficar alinhado ao FIWARE Descomplicado que vocês
  já usam em aula. Trocar para Orion-LD é só mudar a imagem e os paths para `/ngsi-ld/v1/...`.

Se depois quiser aproximar do "FDC de verdade", o próximo passo natural é o repositório
[`FIWARE/data-space-connector`](https://github.com/FIWARE/data-space-connector) (Helm, EDC, ODRL) —
mas para didática em sala, ele tem complexidade de implantação desproporcional ao que dá pra
mostrar numa aula de 1-2h.

## Estrutura

```
dataspace-demo/
├── docker-compose.yaml
├── connector/             # imagem única reaproveitada 3x (producer A, producer B, consumer)
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── simulator/
│   └── index.html         # página única, servida pelo nginx em :8090
└── postman/
    └── data-space-demo.postman_collection.json
```

## Rodando em Apple Silicon (M1–M5)

A imagem `fiware/orion` (Orion clássico, mantida pela Telefónica) não publica build nativo
`arm64` — só `amd64`. Por isso o `docker-compose.yaml` já força `platform: linux/amd64` nos
serviços `orion-a` e `orion-b`, e o Docker Desktop roda essas duas via Rosetta 2 automaticamente.
Os demais serviços (`mongo` oficial, o conector em Python e o `nginx` do simulador) já têm build
nativo `arm64` e não precisam de emulação.

Antes de rodar, confira em Docker Desktop → *Settings → General* se **"Use Rosetta for x86/amd64
emulation on Apple Silicon"** está marcado — isso deixa a emulação do Orion bem mais rápida do que
o QEMU padrão. Num M5 isso é imperceptível pra essa demo (poucas entidades, poucas requisições);
não tente rodar uma carga real assim, só para fins didáticos.

Se preferir eliminar a emulação por completo, a alternativa é trocar `fiware/orion` por
`fiware/orion-ld`, que tem builds mais recentes e maior chance de manifest multi-arch — mas aí a
API muda de NGSI-v2 para NGSI-LD (`/ngsi-ld/v1/...`), o que exige ajustar `app.py` e os `seeds`.
Não fiz essa troca aqui porque o objetivo era ficar compatível com o FIWARE Descomplicado.

## Publicando uma nova entidade como oferta (catálogo dinâmico)

O catálogo deixou de ser fixo: cada produtor nasce com o asset configurado por variável de
ambiente, mas você pode publicar novos assets em runtime com dois passos:

1. **Criar a entidade no Orion**, direto via NGSI-v2 (`POST http://<host>:1026/v2/entities`),
   sem passar pelo conector — é só a sua aplicação de origem gerando dado de contexto, igual
   sempre fez.
2. **Registrar essa entidade como oferta no conector** (`POST /assets` no conector do produtor),
   informando `assetId`, `entityType`, `entityId` e a política daquele asset específico
   (`purpose`, `ttlMinutes`, `allowRedistribution`). A partir daí ela aparece no `/catalog` e pode
   ser negociada, transferida e usada normalmente.

A pasta `6 - Nova entidade e nova oferta` na collection Postman faz exatamente esses dois passos
e, de propósito, registra a nova oferta com `allowRedistribution: true` — pra você contrastar em
aula com o asset original (`AirQualityObserved`, que bloqueia redistribuição): a política é por
asset, não por produtor.

**Importante**: pra rodar essa pasta a partir do seu computador (não de dentro da rede Docker),
o Security Group da instância precisa liberar a porta `1026` (Orion A) além das já liberadas
8080-8082 e 8090. O simulador web não usa essa pasta — ela é só Postman, por enquanto.

## Solução de problemas (coisas que já apareceram de verdade)

- **Página abre mas nada funciona, console mostra `NetworkError`**: o simulador usa o mesmo host
  pelo qual a página foi acessada (`window.location.hostname`) pra montar os endereços dos
  conectores — então funciona igual em `localhost`, numa VM, ou no IP público da nuvem. Se ainda
  assim falhar, confira se as portas 8080, 8081, 8082 e 8090 estão liberadas no Security Group (ou
  firewall equivalente); a 8090 abrir e as outras não é o sintoma mais comum.
- **`/seed` ou `/transfer` falham mas `/catalog` funciona**: esses dois são os únicos passos que o
  conector realmente encaminha pro Orion (os outros só leem config local). Se falhar especificamente
  aqui, o problema está entre conector e Orion, não entre navegador e conector.
- **Erro de DNS (`Temporary failure in name resolution`) só na primeira tentativa**: é uma corrida
  de inicialização do DNS interno do Docker; o `app.py` já tenta de novo automaticamente (5x, com
  pequena espera) antes de devolver erro.
- **Erro 502 mesmo depois do retry, e `docker compose ps -a` mostra `orion-a`/`orion-b` como
  `Exited (0)`**: o Orion saiu por conta própria, não foi derrubado — geralmente é opção de linha de
  comando que essa versão da imagem não reconhece mais. `-dbhost` foi descontinuado em favor de
  `-dbURI` nas builds recentes do `fiware/orion`; o compose já usa `-dbURI mongodb://orion-X:27017/orion`.
  Se trocar a tag da imagem no futuro, vale checar `curl localhost:1026/version` pra confirmar a
  versão e revisitar as opções aceitas.
- **`/seed` retorna 400 com `"date has invalid format in attribute value"`**: o NGSI-v2 exige
  datas em milissegundos com `Z` (`2026-06-18T13:37:28.651Z`), não o `isoformat()` padrão do Python
  (que gera microssegundos + `+00:00`). O `app.py` já usa um formatador dedicado (`ngsi_date`) só
  para esse campo.
- **`Exited (137)` em qualquer container, ou tudo fica lento/trava**: isso sim é falta de memória.
  O stack inteiro (2 Mongo + 2 Orion + 3 conectores + nginx) pede pelo menos uns 1.5-2 GB de RAM
  confortáveis; numa instância de 1 GB (t2/t3.micro) é fácil o OOM killer entrar em ação. O compose
  já limita o cache do WiredTiger de cada Mongo pra 0.25 GB e tem `restart: unless-stopped` em tudo
  (se algo cair, volta sozinho), mas se isso ficar repetindo, o caminho é subir pra `t3.small` (2 GB)
  ou maior durante a aula.

## Como rodar


```bash
cd dataspace-demo
sudo docker compose up -d --build
```

Serviços expostos:

| Serviço | Porta | Papel |
|---|---|---|
| `orion-a` | 1026 | Broker do Produtor A (qualidade do ar) |
| `connector-a` | 8080 | Conector do Produtor A |
| `orion-b` | 1027 | Broker do Produtor B (mobilidade) |
| `connector-b` | 8081 | Conector do Produtor B |
| `connector-consumer` | 8082 | Conector do Consumidor |
| `simulator` | 8090 | Página web da demo |

Token de confiança usado em todas as chamadas: `dataspace-demo-trust-2026` (já vem configurado no
simulador e na collection — só precisa mudar se você alterar o `SHARED_TOKEN` no compose).

## Dois jeitos de demonstrar

- **Simulador web** (`http://localhost:8090`): pensado pra projetar em aula. Cada fase é um botão;
  o ticket de cada acordo mostra a contagem regressiva até a expiração da política em tempo real, e
  o botão "tentar redistribuir" gera o bloqueio visível ao vivo.
- **Collection Postman**: mesmas 5 fases, em pastas numeradas, pra quem quiser ver o request/response
  bruto e explicar cabeçalho por cabeçalho. Importe o JSON, rode pasta por pasta de cima para baixo —
  as variáveis de acordo (`agreementA`, `policyA`, `dataA` etc.) são preenchidas automaticamente por
  scripts de teste a cada passo.

## O momento que vale a aula

Depois do passo 4 (consumidor recebeu os dados), tente:

1. **Visualizar** → permitido (a política autoriza esse propósito).
2. **Redistribuir** → bloqueado pelo conector do consumidor, mesmo o dado já estando no disco dele.

Esse é o argumento central de soberania de dados: o controle não depende de onde o dado está
fisicamente, depende da política que viaja com ele e é reforçada em cada novo uso — inclusive
depois da transferência ter terminado. Depois do TTL (5 minutos por padrão, ajustável via
`POLICY_TTL_MINUTES` no compose), até a visualização passa a ser bloqueada por expiração.
