# Dataset do experimento (Fase 10)

Ver `.cursor/specs/fase10.spec.md`, seções 1 e 4, para a metodologia completa.
Este arquivo documenta só o **formato** que `auditor.experiment.run_experiment`
(`scripts/run_experiment.py`) espera encontrar aqui — ele não contém nenhum
caso do dataset em si. Os casos são curados por revisão humana, não gerados
por ferramenta nenhuma (regra não negociável da seção 1: rotular olhando a
saída do sistema seria viés circular).

## Layout

```
dataset/experiment/
  <model_name>/              # um por Smart Data Model incluído (ex.: Streetlight)
    <case_id>/                # um por caso — nome livre, só precisa ser único dentro do modelo
      entity.json              # a entidade NGSI-v2 completa
      ground_truth.json         # o rótulo de verdade desse caso
    <outro_case_id>/
      entity.json
      ground_truth.json
  <outro_model_name>/
    ...
```

`<model_name>` é só o nome do diretório — o tipo NGSI real usado para agrupar
os casos em auditorias (`POST /audits` por tipo, seção 2) vem do campo
`"type"` dentro de cada `entity.json`, nunca do nome da pasta.

## `entity.json`

A entidade NGSI-v2 completa, no mesmo formato usado para popular o Orion real
(o mesmo que os fixtures de `tests/fixtures/*.json` da Fase 1) — `id`, `type`
e cada atributo como `{"type": ..., "value": ..., "metadata": {}}`.

## `ground_truth.json`

```json
{
  "expected_violations": [
    {
      "rule": "attribute_name_synonym",
      "attribute_path": "temperature",
      "severity": "error",
      "detected_by": "semantic",
      "proposed_patch": {"from": "temp", "to": "temperature"}
    }
  ]
}
```

Cada item de `expected_violations` mapeia 1:1 para
`auditor.experiment.metrics.ExpectedViolation`:

| Campo | Valores | Nota |
|---|---|---|
| `rule` | string livre | mesma convenção de `Violation.rule` (`StructuralValidator`) ou o `rule` que o Nível 2 usar para o achado |
| `attribute_path` | string | caminho do atributo na entidade |
| `severity` | `"error"` \| `"warning"` \| `"info"` | `ViolationSeverity` |
| `detected_by` | `"structural"` \| `"semantic"` | qual nível **deveria** pegar essa violação — é o que decide em qual categoria do dataset (tabela da seção 1) o caso entra |
| `proposed_patch` | objeto ou `null` | só quando o caso também espera uma `Recommendation` — mesmo formato livre de `Recommendation.proposed_patch` (ex.: `{"from": "temp", "to": "temperature"}` para `rename_attribute`) |

Uma entidade sem nenhuma violação esperada (categoria "Conformantes", seção 1)
tem `"expected_violations": []`.

## Categorias (seção 1) e o que cada uma exige do rótulo

| Categoria | `expected_violations` |
|---|---|
| Conformantes | `[]` |
| Não conformantes estruturais (óbvias) | um ou mais itens com `detected_by: "structural"` |
| Não conformantes semânticas (invisíveis ao Nível 1) | um ou mais itens com `detected_by: "semantic"` — a categoria central do TCC (métrica 3.2) |
| Ambíguas/limítrofes | depende do caso específico (ver nota do `StructuralValidator`, Fase 1, sobre a regra `anyOf`) |

## Regra não negociável (reforço da seção 1/4)

`ground_truth.json` é escrito **antes** de rodar `run_experiment.py` contra o
caso, nunca ajustado depois de ver a saída do sistema. Se um resultado
"parecer errado", a checagem é contra este arquivo como já estava escrito —
nunca o inverso.

## Validando o dataset em si (seção 1.1)

Antes de reportar qualquer número na monografia, confirme que:

1. toda violação estrutural rotulada aqui realmente corresponde ao que
   `StructuralValidator` produziria contra o schema real do modelo
   (`SchemaCatalogPort.fetch_schema`, ao vivo);
2. nenhuma violação rotulada como `detected_by: "semantic"` seria detectada
   rodando só o Nível 1 (sem SLM) — senão o caso está na categoria errada.

`auditor.experiment.run_experiment.load_dataset()` só valida a *forma* dos
arquivos (JSON bem formado, campos obrigatórios presentes); as duas checagens
acima são sobre o *conteúdo* do rótulo e continuam sendo responsabilidade de
quem cura o dataset.
