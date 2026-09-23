# Guia de curadoria do glossário de sinônimos (RAG — Nível 2)

**Para quem vai fazer:** você não precisa entender o sistema inteiro, nem rodar banco de
dados, nem SLM. A tarefa é só editar um arquivo YAML seguindo um formato exato. Este guia
cobre só essa tarefa — nada além dela.

---

## 1. Contexto rápido (o que isso é e por quê)

A ferramenta audita entidades comparando-as contra o schema oficial de um Smart Data Model.
Ela tem duas camadas:

- **Nível 1** (validação estrutural): confere campo por campo contra o schema. Sozinho, se
  uma entidade tem o atributo `temp` em vez do atributo oficial `temperature`, o Nível 1 só
  sabe dizer "`temperature` está ausente" — ele não sabe que `temp` é provavelmente a mesma
  coisa com o nome errado.
- **Nível 2** (SLM + RAG): é quem faz essa ligação — "`temp` é provavelmente `temperature`
  com nome errado, sugiro renomear". Mas ele só consegue fazer essa ligação se alguém tiver
  escrito, antes, que `temp` é um sinônimo conhecido de `temperature`. Essa lista de
  sinônimos por atributo é o **glossário** — vive em `knowledge/synonyms.yaml` — e é
  curadoria humana, não algo que o sistema descobre sozinho.

Sem uma entrada no glossário para os atributos de um modelo novo, o Nível 2 não tem nada
para recuperar sobre esse modelo — é só isso que falta pra ele funcionar num modelo que
ainda não foi coberto.

**Você não precisa decidir nada além disso.** Não é sua tarefa escolher quais Smart Data
Models entram no experimento, nem escrever entidades de teste, nem o `ground_truth.json` —
isso é feito à parte. Sua entrega é só o(s) arquivo(s) YAML descrito(s) abaixo, para
o(s) modelo(s) que te passarem.

---

## 2. O que você vai produzir

Um bloco novo, no fim de `knowledge/synonyms.yaml`, com uma entrada por atributo canônico
que você decidir cobrir daquele modelo. Formato exato (é assim que já está escrito hoje,
para o Streetlight):

```yaml
- id: synonym-illuminance-level
  canonical: illuminanceLevel
  seen_as: [lum, illuminance, luminosity]

- id: synonym-temperature
  canonical: temperature
  seen_as: [temp, tempC, temperatura]
```

Cada entrada tem exatamente três campos:

| Campo | O que é | Regra |
|---|---|---|
| `id` | Identificador único da entrada | Convenção: `synonym-<nome-canônico-em-kebab-case>` (ex.: `illuminanceLevel` → `synonym-illuminance-level`). Precisa ser único em **todo** o corpus (`knowledge/*.yaml` inteiro, não só neste arquivo) — se repetir um `id` que já existe em qualquer um dos quatro arquivos, o sistema rejeita com erro apontando o `id` duplicado. |
| `canonical` | O nome do atributo exatamente como está no schema oficial do Smart Data Model | Copie do schema, não invente — inclusive a capitalização (`lowerCamelCase`, ex.: `windSpeed`, não `wind_speed` nem `Windspeed`). |
| `seen_as` | Lista de variações/erros comuns pelas quais esse atributo aparece na prática | Lista entre `[colchetes]`, itens separados por vírgula, sem aspas a menos que o item tenha caracteres especiais. Pelo menos 1 item; normalmente 2-4 bastam. |

---

## 3. Passo a passo

### Passo 0 — confira se o atributo já está coberto

Antes de escrever qualquer coisa nova, abra `knowledge/synonyms.yaml` e veja se o atributo
que você quer cobrir já tem entrada (ex.: `address`, `dateCreated`/`dateModified` e outros
atributos comuns a vários modelos podem já estar lá). Se já estiver, não crie uma entrada
duplicada — só adicione sinônimos novos que faltarem na lista `seen_as` existente, se algum
vier à mente.

### Passo 1 — pegue o schema oficial do modelo

Vá em [smartdatamodels.org](https://smartdatamodels.org) (ou peça o link exato de quem te
passou a tarefa) e abra o `schema.json` do modelo. Você vai olhar dois lugares dentro dele:

- `required`: os atributos obrigatórios — são os candidatos mais importantes a cobrir.
- `properties`: a lista completa de atributos, com o `type` de cada um.

### Passo 2 — escolha quais atributos vale cobrir

Não precisa (nem compensa) cobrir todo atributo do modelo. Priorize os que são:

1. **Obrigatórios** (`required`) — são os que geram violação `ERROR` quando ausentes, então
   são os que mais valem a pena ter um sinônimo mapeado.
2. **Do tipo que, na prática, as pessoas abreviam ou nomeiam de forma inconsistente** —
   grandezas físicas (temperatura, umidade, velocidade, pressão), datas, unidades,
   identificadores. Atributos muito específicos e sem ambiguidade de nome (ex.: um enum com
   um nome já bem óbvio) geralmente não precisam de entrada.

Duas a cinco atributos por modelo já é uma cobertura razoável — não é preciso esgotar a
lista.

### Passo 3 — levante os sinônimos de cada atributo escolhido

Aqui é julgamento, não uma busca mecânica. Pergunte-se, para cada atributo canônico: **se
alguém não tivesse lido o schema oficial, como essa pessoa provavelmente chamaria esse
campo?** Fontes de ideia:

- Abreviações comuns em inglês (`temp`, `hum`, `addr`, `loc`).
- A tradução literal em português, já que os dados de origem no seu projeto podem vir
  traduzidos (`temperatura`, `umidade`, `endereco`, `velocidade`).
- Como o mesmo tipo de grandeza aparece nomeado em *outros* Smart Data Models ou em fontes
  de dados públicas reais desse domínio (ex.: um dataset de estacionamento real que você
  conheça) — nomes que "quase acertam" o atributo certo.
- Erros de capitalização/separador que ainda sejam candidatos plausíveis a se confundir com
  o nome certo (não vale colocar qualquer string aleatória).

**Exemplo ilustrativo completo** (modelo `WeatherObserved`, oficial da FIWARE — só para
mostrar o raciocínio, não é um modelo que necessariamente está no seu experimento):

Atributo canônico `relativeHumidity` (obrigatório, tipo Number, 0.0–1.0):
- Pensando nos sinônimos: `humidity` (nome mais genérico, sem o "relative"), `hum`
  (abreviação comum, já usada no exemplo de `humidity` do Streetlight), `umidade`
  (tradução).

Entrada resultante:
```yaml
- id: synonym-relative-humidity
  canonical: relativeHumidity
  seen_as: [humidity, hum, umidade]
```

Atributo canônico `windSpeed` (tipo Number, m/s):
```yaml
- id: synonym-wind-speed
  canonical: windSpeed
  seen_as: [wind, velocidadeVento, windspeed]
```

### Passo 4 — escreva as entradas no arquivo

Abra `knowledge/synonyms.yaml` e adicione suas entradas novas no final da lista, no mesmo
formato do Passo 2 acima. Não precisa se preocupar com ordem — o arquivo é uma lista simples,
sem agrupamento por modelo.

### Passo 5 — verifique seu próprio trabalho antes de entregar

Isso não precisa de banco de dados nem de nenhuma dependência pesada, só do Python do
projeto já configurado. Na raiz do repositório, rode:

```
pytest tests/unit/infrastructure/rag/test_corpus_loader.py -v
```

Se aparecer `passed` em tudo, seu YAML está sintaticamente correto, sem `id` duplicado e com
todos os campos obrigatórios. Se der erro, a mensagem aponta exatamente o `id` problemático
e o que falta — corrija e rode de novo.

Esse é o fim da sua parte. A indexação de fato (gerar os embeddings e colocar no banco
vetorial) é feita depois, por quem estiver com o ambiente completo configurado — não é algo
que você precisa rodar.

---

## 4. Opcional: casos anotados (`knowledge/annotated_cases.yaml`)

Isso é enriquecimento, não obrigatório — só vale a pena se, ao pesquisar o modelo, você
encontrar um padrão de erro específico e ilustrativo que os sinônimos por si só não
capturam bem (ex.: um formato de valor errado, não só um nome de atributo errado). Mesmo
formato dos exemplos já existentes:

```yaml
- id: case-<slug-descritivo>
  tags: [<tag-livre>, <atributo-relacionado>]
  incorrect_example: '<JSON do trecho da entidade, errado>'
  explanation: >
    <por que está errado, em 1-2 frases>
  correction: >
    <JSON do trecho corrigido>
```

Todos os quatro campos (`id`, `incorrect_example`, `explanation`, `correction`) são
obrigatórios aqui — se faltar algum, o mesmo comando de verificação do Passo 5 vai apontar o
erro.

---

## 5. Checklist final antes de entregar

- [ ] Cada atributo novo coberto tem o nome **exatamente** como aparece no `schema.json`
      oficial (capitalização inclusa).
- [ ] Nenhum `id` novo repete um `id` que já existe em qualquer arquivo de `knowledge/`.
- [ ] `pytest tests/unit/infrastructure/rag/test_corpus_loader.py -v` passou sem erros.
- [ ] Você não precisou tocar em nenhum outro arquivo do projeto além de
      `knowledge/synonyms.yaml` (e, se aplicável, `knowledge/annotated_cases.yaml`).
