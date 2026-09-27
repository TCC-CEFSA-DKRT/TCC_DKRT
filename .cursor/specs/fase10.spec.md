# Specs — Fase 10: Experimento e Métricas

Última fase do plano geral (Parte V): **é esta fase que produz os resultados do TCC** — as
fases 1–9 produzem o instrumento, esta fase o usa para medir algo defensável perante a
banca. Formato adaptado: além de contrato + dado/quando/então (aqui aplicados ao **código
de medição em si**, seção 6 — o instrumento de medir também pode ter bug), esta fase define
metodologia experimental, que precisa ser tão explícita quanto qualquer contrato de
`Protocol` das fases anteriores.

---

## 1. Dataset controlado

**O auditor sempre foi pensado no plural — audita entidades de qualquer Smart Data Model
resolvível no catálogo (`SchemaCatalogPort`, Fase 2), não um único modelo travado.** O
dataset do experimento reflete isso: cobre **mais de um Smart Data Model** do catálogo,
reaproveitando os fixtures da Fase 1 (`streetlight_conformant.json`,
`streetlight_partial.json`, `streetlight_non_conformant.json`) como o primeiro deles — não
como o único. `temp`/`temperature` no Streetlight é o caso já validado ponta a ponta pelo
teste golden (Fase 7) e serve de exemplo recorrente no restante do plano, mas é um exemplo
do fenômeno (sinônimo presente no lugar do atributo canônico), não a definição dele.

Cada modelo incluído ganha, além das entidades, uma categoria nova que as fases anteriores
não precisavam isolar: entidades cujo problema só é detectável no Nível 2.

| Categoria | Composição | Propósito |
|---|---|---|
| Conformantes | N entidades por modelo sem nenhum problema | Mede falso positivo (o sistema não deve inventar violação onde não há) |
| Não conformantes estruturais (óbvias) | N entidades por modelo com violação que o Nível 1 comprovadamente pega (campo ausente, tipo errado, `enum` inválido — mesmos tipos de regra do `StructuralValidator`, Fase 1) | Mede acurácia do Nível 1 isoladamente |
| Não conformantes semânticas (invisíveis ao Nível 1) | N entidades por modelo com o padrão de sinônimo (atributo presente no lugar do canônico, atributo canônico ausente) — `temp`/`temperature` no Streetlight, e o equivalente curado para cada outro modelo do dataset | **A métrica central do TCC** — mede o que o Nível 2 adiciona sobre o Nível 1 sozinho, e que isso generaliza além de um único modelo |
| Ambíguas/limítrofes | N entidades por modelo desenhadas para estressar o limite do Nível 1 (ver nota do `StructuralValidator`, Fase 1 — regra `anyOf`, primeira alternativa como expectativa canônica) | Garante que o experimento também cobre os casos que o próprio código já documenta como decisão de design não-trivial |

`N` por categoria **e quantos/quais modelos além do Streetlight entram no dataset** são
decididos na implementação — dois eixos do mesmo trade-off de tempo disponível: cada
entidade da categoria semântica custa uma chamada ao SLM (seção 3 abaixo, real, não
mockada), e cada modelo novo custa curadoria de conhecimento (Fase 6 — hoje
`knowledge/synonyms.yaml` só cobre `illuminanceLevel`/`temperature`/`humidity`/`address`;
sem sinônimo curado para os atributos de um modelo novo, o Nível 2 não tem o que recuperar
via RAG para ele). Escolher poucos modelos adicionais e curar bem vale mais, para o
experimento, do que cobrir muitos rasos — mas o dataset não pode ficar em um só.

Vive em `dataset/experiment/<model_name>/` (um diretório por Smart Data Model incluído) —
cada entidade com:
- a entidade NGSI-v2 completa (mesmo formato usado para popular o Orion real, Fase 4);
- o **rótulo de verdade** (`ground_truth.json`): violações esperadas (`rule`,
  `attribute_path`, `severity`, `detected_by` esperado — `STRUCTURAL` ou `SEMANTIC`) e,
  quando aplicável, o `proposed_patch` correto esperado de uma `Recommendation`.

**Regra metodológica não negociável:** o rótulo de verdade é escrito por revisão humana
**antes** de rodar o sistema contra o dataset — nunca ajustado depois de ver a saída do
sistema. Rotular olhando a saída seria viés circular (o sistema "acertaria" por
construção, não por mérito) — o tipo de erro que invalidaria os resultados perante a banca.

### 1.1 Casos de teste (do dataset em si)

- **Dado** o dataset completo, **quando** cada `ground_truth.json` é validado contra o
  schema real do **modelo correspondente daquela entidade** (`SchemaCatalogPort.fetch_schema`,
  Fase 2, ao vivo — nunca hardcoded a um único modelo, já que o dataset cobre mais de um),
  **então** toda violação estrutural rotulada como esperada realmente corresponde a uma
  violação que o `StructuralValidator` (Fase 1) produziria — um rótulo de verdade errado
  quebraria a medição antes mesmo do sistema entrar em cena.
- **Dado** a categoria "não conformantes semânticas", **quando** processada só pelo Nível 1
  (sem SLM), **então** nenhuma das violações-alvo desta categoria é detectada — é a
  confirmação de que a categoria realmente testa o que se propõe a testar (se o Nível 1
  sozinho já pegasse, a entidade estaria na categoria errada).

---

## 2. Execução do experimento

Contra o sistema real e completo (Fases 4–7): dataset carregado no Orion real
(`docker-compose`, mesmo ambiente das Fases 4/5), `POST /audits` disparando o fluxo
completo (fila → worker → Nível 1 → Nível 2 quando aplicável, Fase 5/7), SLM real via
Ollama/Qwen2.5 (ou Bedrock, conforme decidido na Fase 9). **Nunca mockado** — resultado de
experimento contra fakes não mede nada sobre o sistema real.

Cada execução registra, por entidade: `EntityReport` completo (Fases 1–7), timestamp de
início/fim do processamento daquela entidade especificamente (não só do run inteiro — Fase
5 já expõe `processed`/`total` por run, mas o experimento precisa de granularidade por
entidade para a métrica de tempo, seção 3.3), e, quando o Nível 2 rodou, os tokens
consumidos na chamada ao SLM (Ollama expõe isso na resposta; Bedrock, no billing).

---

## 3. Métricas (plano geral, seção "Fase 10")

### 3.1 Acurácia por nível

Precision/recall/F1 comparando violações **detectadas** (`EntityReport.violations`,
filtradas por `detected_by`) contra violações **esperadas** (`ground_truth.json`),
calculado separadamente para `detected_by=STRUCTURAL` e `detected_by=SEMANTIC` — nunca uma
métrica única misturando os dois níveis, porque a pergunta científica é justamente "o
quanto cada nível contribui", não "o sistema como caixa-preta".

### 3.2 Violações exclusivas do SLM

```
exclusivas_do_slm = { v in ground_truth : v só é detectável com Nível 2 rodando }
detectadas_pelo_slm = { v in exclusivas_do_slm : existe Violation(detected_by=SEMANTIC)
                        correspondente no EntityReport }
taxa = |detectadas_pelo_slm| / |exclusivas_do_slm|
```

Esta é a métrica que sustenta a frase do plano geral ("o sistema detecta `temp` vs
`temperature` — uma violação que o Nível 1 comprovadamente não pega") como número, não só
demonstração pontual (a demonstração pontual já existe como teste golden, Fase 7, seção 7)
— aqui é a **taxa** sobre todo o dataset da categoria correspondente (seção 1).

### 3.3 Tempo por entidade

Distribuição (p50/p95/máximo) do tempo de processamento por entidade, separada em duas
séries: entidades que só passaram pelo Nível 1 vs. entidades que também passaram pelo
Nível 2 — quantifica o custo real de latência do SLM sobre o caminho rápido, o mesmo
trade-off que justificou a fila assíncrona (Fase 5) e o controle de custo (Fase 7, seção 3)
desde o desenho, agora com número real em vez de intuição.

### 3.4 Custo de inferência

Se Bedrock (Fase 9, seção 6): `tokens consumidos × preço por 1k tokens do modelo`, somado
por auditoria completa e por entidade média. Se Ollama local: não há custo monetário de
API, então a métrica reportada é **tempo de CPU/GPU consumido por entidade** como proxy
honesto de custo computacional — a monografia deve deixar essa diferença de unidade
explícita, nunca comparar os dois em `$` como se fossem a mesma grandeza quando a decisão
da Fase 9 escolheu Ollama.

### 3.5 Taxa de alucinação nas recomendações

Definição operacional, necessária porque "alucinação" sozinho é vago demais para virar
número: uma `Recommendation` é contada como **alucinada** quando pelo menos uma destas
condições é verdadeira, checada contra o `ground_truth.json` e o schema real:
1. `attribute_path` não existe no schema do modelo (o SLM inventou um nome de atributo);
2. `proposed_patch`, se aplicado à entidade original, **não** resolve a violação que a
   `Recommendation` alega corrigir (verificável programaticamente: aplica o patch e roda o
   `StructuralValidator`, Fase 1, de novo — se a violação correspondente continua
   presente, o patch não fez o que disse que faria);
3. `action` (`RecommendationAction`, Fase 1) não corresponde ao tipo de violação que
   supostamente resolve (ex.: `fix_type` para uma violação que era, na verdade,
   `required_property_missing`).

```
taxa_alucinacao = |recomendacoes alucinadas| / |total de recomendacoes emitidas|
```

Cada condição é individualmente contável na monografia (não só a taxa agregada) — permite
distinguir "o modelo erra o nome do atributo" de "o modelo propõe um patch que não resolve
nada", diagnósticos diferentes com implicações diferentes para trabalho futuro.

---

## 4. Metodologia — evitar viés circular (reforço da seção 1)

- Rótulos de verdade nunca ajustados após ver a saída do sistema (seção 1).
- Nenhum ajuste de prompt (Fase 7) ou de threshold nesta fase **depois** de rodar o
  experimento e ver os números — isso seria otimizar para o próprio conjunto de teste. Se
  um ajuste for necessário, exige um dataset de validação **separado** do dataset de
  experimento final reportado na monografia, nunca o mesmo.
- A pessoa que rotula o `ground_truth.json` (seção 1) não deveria também ser quem, depois,
  decide se um resultado "parece razoável" sem checar contra o rótulo escrito antes —
  reduz o risco de racionalizar um resultado ruim como aceitável.

---

## 5. Relatório de resultados — formato reprodutível

Um script único (`scripts/run_experiment.py` ou equivalente) que: carrega o dataset (seção
1) no Orion real, dispara as auditorias (seção 2), aguarda conclusão via polling (`GET
/audits/{id}/progress`, Fase 5), calcula as cinco métricas (seção 3) e grava um relatório
(`results/experiment-<data>.json` + uma tabela Markdown pronta para colar na monografia).
Reprodutível: rodar o script duas vezes com o mesmo dataset e o mesmo SLM/versão de modelo
produz números iguais (dentro da variação inerente ao SLM — ver nota sobre não-determinismo
no teste golden, Fase 7, seção 7) ou explicavelmente próximos, nunca resultados
inexplicavelmente diferentes que sugerem um bug de medição.

---

## 6. Casos de teste — do próprio código de medição

Um script de métricas com bug invalidaria o experimento inteiro mesmo com o sistema
correto — por isso o cálculo das métricas (seção 3) é testado como qualquer outro
componente das fases anteriores, com fixtures sintéticas de resultado **conhecido**, sem
depender do sistema real nem do SLM:

- **Dado** um `EntityReport` sintético com violações conhecidas e um `ground_truth`
  sintético também conhecido, **quando** a função de precision/recall (seção 3.1) roda,
  **então** o resultado bate com o cálculo manual esperado (caso de teste com números
  simples, verificáveis à mão).
- **Dado** uma `Recommendation` sintética cujo `proposed_patch`, aplicado, **não** resolve
  a violação (caso construído deliberadamente), **quando** a função de detecção de
  alucinação (seção 3.5, condição 2) roda, **então** classifica corretamente como
  alucinada — e o caso simétrico (patch que resolve de verdade) **não** é classificado
  como alucinado, testado lado a lado para garantir que a função não superestima nem
  subestima sistematicamente.
- **Dado** um conjunto vazio de recomendações, **quando** a taxa de alucinação (seção 3.5)
  é calculada, **então** o resultado é reportado como "sem dados" (`None`/`N/A`), nunca uma
  divisão por zero silenciosa nem um `0%` que seria indistinguível de "zero alucinações
  observadas em muitas recomendações".

---

## 7. Fora de escopo desta fase

- Comparação com ferramentas concorrentes de validação de conformidade FIWARE/NGSI — fora
  do escopo deste TCC, registrado como trabalho futuro na monografia.
- Qualquer otimização de prompt/modelo motivada pelos números vistos nesta fase (seção 4) —
  isso seria a próxima iteração do projeto, não parte desta medição.
- Escrita da monografia em si — esta fase produz os **dados e o relatório reprodutível**
  (seção 5) que alimentam o capítulo de resultados; a redação, discussão e conclusão são
  trabalho de escrita, não de engenharia, e não têm caso de teste.

---

## 8. Definição de pronto da Fase 10

- Dataset controlado (seção 1) curado, rotulado por humano **antes** de rodar o sistema,
  versionado em `dataset/experiment/`, cobrindo **mais de um Smart Data Model** do catálogo
  (Streetlight e ao menos um outro) — não apenas o modelo usado nos fixtures de TDD da
  Fase 1.
- Script de execução (seção 5) reprodutível, rodado contra o sistema completo e real
  (Orion real, SLM real conforme decisão da Fase 9) — nenhum resultado reportado na
  monografia vem de um mock.
- As cinco métricas (seção 3) calculadas e reportadas, com o código de cálculo testado
  isoladamente (seção 6) contra fixtures de resultado conhecido.
- Taxa de violações exclusivas do SLM (seção 3.2) é o número que sustenta, com dados, a
  alegação central do TCC — não fica só como demonstração pontual (teste golden, Fase 7).
- Relatório reprodutível (`results/experiment-<data>.json` + tabela Markdown) pronto para
  ser citado diretamente no capítulo de resultados da monografia.
